from __future__ import annotations

import sys
import unittest
from pathlib import Path

import torch


MODEL_DIRECTORY = Path(__file__).resolve().parents[1] / "user_data" / "freqaimodels"
sys.path.insert(0, str(MODEL_DIRECTORY))

from PyTorchSequenceRegressor import RecurrentReturnModel, TransformerReturnModel


class SequenceModelTests(unittest.TestCase):
    def test_recurrent_models_keep_freqai_output_shape(self) -> None:
        for cell_type in ("RNN", "GRU", "LSTM"):
            with self.subTest(cell_type=cell_type):
                model = RecurrentReturnModel(
                    input_dim=18, output_dim=1, cell_type=cell_type
                )
                output = model(torch.randn(4, 48, 18))
                self.assertEqual(output.shape, (4, 1, 1))

    def test_transformer_keeps_freqai_output_shape(self) -> None:
        model = TransformerReturnModel(
            input_dim=18,
            output_dim=1,
            max_seq_len=48,
            d_model=32,
            nhead=4,
            num_layers=1,
            dim_feedforward=64,
        )
        output = model(torch.randn(4, 48, 18))
        self.assertEqual(output.shape, (4, 1, 1))

    def test_transformer_rejects_window_longer_than_position_embedding(self) -> None:
        model = TransformerReturnModel(input_dim=18, output_dim=1, max_seq_len=48)
        with self.assertRaisesRegex(ValueError, "exceeds configured maximum"):
            model(torch.randn(2, 49, 18))

    def test_transformer_requires_head_dimension_to_divide_model_dimension(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be divisible"):
            TransformerReturnModel(
                input_dim=18,
                output_dim=1,
                max_seq_len=48,
                d_model=30,
                nhead=4,
            )


if __name__ == "__main__":
    unittest.main()
