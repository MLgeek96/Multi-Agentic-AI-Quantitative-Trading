from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import torch
from torch import nn

# Freqtrade loads user models dynamically.  Keeping this directory importable
# also lets torch.load re-import the custom classes when FreqAI restores a model.
_MODEL_DIRECTORY = str(Path(__file__).resolve().parent)
if _MODEL_DIRECTORY not in sys.path:
    sys.path.insert(0, _MODEL_DIRECTORY)

from freqtrade.freqai.base_models.BasePyTorchRegressor import BasePyTorchRegressor
from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
from freqtrade.freqai.torch.PyTorchDataConvertor import (
    DefaultPyTorchDataConvertor,
    PyTorchDataConvertor,
)
from freqtrade.freqai.torch.PyTorchModelTrainer import PyTorchTransformerTrainer


class RecurrentReturnModel(nn.Module):
    """Small many-to-one recurrent regressor for a rolling candle window."""

    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        cell_type: str = "GRU",
        hidden_dim: int = 32,
        num_layers: int = 1,
        dropout: float = 0.0,
    ) -> None:
        super().__init__()
        cell = cell_type.upper()
        recurrent_types = {"RNN": nn.RNN, "GRU": nn.GRU, "LSTM": nn.LSTM}
        if cell not in recurrent_types:
            raise ValueError(f"cell_type must be RNN, GRU, or LSTM, got {cell_type!r}")

        # PyTorch applies recurrent dropout only between stacked layers.
        recurrent_dropout = dropout if num_layers > 1 else 0.0
        self.recurrent = recurrent_types[cell](
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=recurrent_dropout,
        )
        self.head = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        sequence, _ = self.recurrent(x)
        # Match Freqtrade's WindowDataset target shape [batch, 1, labels].
        return self.head(sequence[:, -1, :]).unsqueeze(1)


class TransformerReturnModel(nn.Module):
    """Small encoder-only Transformer for a fixed rolling candle window."""

    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        max_seq_len: int,
        d_model: int = 32,
        nhead: int = 4,
        num_layers: int = 1,
        dim_feedforward: int = 64,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        if d_model % nhead != 0:
            raise ValueError(f"d_model ({d_model}) must be divisible by nhead ({nhead})")

        self.max_seq_len = max_seq_len
        self.input_projection = nn.Linear(input_dim, d_model)
        self.position_embedding = nn.Parameter(torch.empty(1, max_seq_len, d_model))
        nn.init.normal_(self.position_embedding, mean=0.0, std=0.02)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(
            encoder_layer, num_layers=num_layers, enable_nested_tensor=False
        )
        self.head = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Dropout(dropout),
            nn.Linear(d_model, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        sequence_length = x.shape[1]
        if sequence_length > self.max_seq_len:
            raise ValueError(
                f"sequence length {sequence_length} exceeds configured maximum {self.max_seq_len}"
            )
        sequence = self.input_projection(x)
        sequence = sequence + self.position_embedding[:, :sequence_length, :]
        sequence = self.encoder(sequence)
        # Every token is historical at forecast time, so the final token may
        # attend to the complete input window without a causal mask.
        return self.head(sequence[:, -1, :]).unsqueeze(1)


class PyTorchSequenceRegressor(BasePyTorchRegressor):
    """FreqAI adapter selecting a recurrent cell or Transformer encoder."""

    @property
    def data_convertor(self) -> PyTorchDataConvertor:
        return DefaultPyTorchDataConvertor(target_tensor_type=torch.float)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        training = self.freqai_info.get("model_training_parameters", {})
        self.learning_rate = float(training.get("learning_rate", 3e-4))
        self.weight_decay = float(training.get("weight_decay", 1e-4))
        self.random_seed = int(training.get("random_seed", 42))
        self.architecture = str(training.get("architecture", "RECURRENT")).upper()
        self.model_kwargs: dict[str, Any] = training.get("model_kwargs", {})
        self.trainer_kwargs: dict[str, Any] = training.get("trainer_kwargs", {})

    def fit(self, data_dictionary: dict, dk: FreqaiDataKitchen, **kwargs) -> Any:
        # Reset per fold so repeated CPU backtests are reproducible and architecture
        # comparisons are not dominated by a lucky random initialization.
        np.random.seed(self.random_seed)
        torch.manual_seed(self.random_seed)
        n_features = data_dictionary["train_features"].shape[-1]
        n_labels = data_dictionary["train_labels"].shape[-1]
        if self.architecture == "TRANSFORMER":
            model = TransformerReturnModel(
                input_dim=n_features,
                output_dim=n_labels,
                max_seq_len=self.window_size,
                **self.model_kwargs,
            ).to(self.device)
        elif self.architecture == "RECURRENT":
            model = RecurrentReturnModel(
                input_dim=n_features,
                output_dim=n_labels,
                **self.model_kwargs,
            ).to(self.device)
        else:
            raise ValueError(
                "architecture must be RECURRENT or TRANSFORMER, "
                f"got {self.architecture!r}"
            )

        optimizer = torch.optim.AdamW(
            model.parameters(), lr=self.learning_rate, weight_decay=self.weight_decay
        )
        criterion = nn.HuberLoss(delta=1.0)

        trainer = self.get_init_model(dk.pair)
        if trainer is None:
            trainer = PyTorchTransformerTrainer(
                model=model,
                optimizer=optimizer,
                criterion=criterion,
                device=self.device,
                data_convertor=self.data_convertor,
                window_size=self.window_size,
                tb_logger=self.tb_logger,
                **self.trainer_kwargs,
            )
        trainer.fit(data_dictionary, self.splits)
        return trainer

    @torch.no_grad()
    def predict(
        self, unfiltered_df: pd.DataFrame, dk: FreqaiDataKitchen, **kwargs
    ) -> tuple[pd.DataFrame, npt.NDArray[np.int_]]:
        dk.find_features(unfiltered_df)
        prediction_features, _ = dk.filter_features(
            unfiltered_df, dk.training_features_list, training_filter=False
        )
        prediction_features, outliers, _ = dk.feature_pipeline.transform(
            prediction_features, outlier_check=True
        )
        x = self.data_convertor.convert_x(prediction_features, device=self.device).unsqueeze(0)

        self.model.model.eval()
        predictions: list[torch.Tensor] = []
        if x.shape[1] > self.window_size:
            for index in range(x.shape[1] - self.window_size):
                window = x[:, index : index + self.window_size, :]
                predictions.append(self.model.model(window))
            y = torch.cat(predictions, dim=1)
        else:
            y = self.model.model(x)

        values = y.cpu().squeeze(0).detach().numpy()
        if values.ndim == 1:
            values = values.reshape(-1, 1)
        pred_df = pd.DataFrame(values, columns=dk.label_list)
        pred_df, _, _ = dk.label_pipeline.inverse_transform(pred_df)

        if self.ft_params.get("DI_threshold", 0) > 0:
            dk.DI_values = dk.feature_pipeline["di"].di_values
        else:
            dk.DI_values = np.zeros(outliers.shape[0])
        dk.do_predict = outliers

        padding = len(prediction_features) - len(pred_df)
        if padding > 0:
            zeros = pd.DataFrame(np.zeros((padding, len(dk.label_list))), columns=dk.label_list)
            pred_df = pd.concat([zeros, pred_df], axis=0, ignore_index=True)
        return pred_df, dk.do_predict
