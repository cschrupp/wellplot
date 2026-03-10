from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from well_log_os.errors import TemplateValidationError
from well_log_os.logfile import LogFileSpec
from well_log_os.pipeline import render_from_logfile
from well_log_os.renderers.base import RenderResult


class PipelineTests(unittest.TestCase):
    @patch("well_log_os.pipeline.MatplotlibRenderer")
    @patch("well_log_os.pipeline.build_document_for_logfile")
    @patch("well_log_os.pipeline.load_dataset_for_logfile")
    @patch("well_log_os.pipeline.load_logfile")
    def test_render_from_logfile_uses_master_matplotlib_loader(
        self,
        mock_load_logfile,
        mock_load_dataset,
        mock_build_document,
        mock_renderer_class,
    ) -> None:
        spec = LogFileSpec(
            name="test",
            data_source_path="input.las",
            data_source_format="las",
            render_backend="matplotlib",
            render_output_path="result.pdf",
            render_dpi=320,
            document={"name": "test"},
        )
        dataset = Mock(name="dataset")
        document = Mock(name="document")
        mock_load_logfile.return_value = spec
        mock_load_dataset.return_value = (dataset, Path("/tmp/input.las"))
        mock_build_document.return_value = document
        renderer = mock_renderer_class.return_value
        renderer.render.return_value = RenderResult(
            backend="matplotlib",
            page_count=1,
            output_path=Path("/tmp/result.pdf"),
        )

        result = render_from_logfile("/tmp/config.log.yaml")
        self.assertEqual(result.backend, "matplotlib")
        mock_renderer_class.assert_called_once_with(dpi=320)
        renderer.render.assert_called_once()
        called_output = renderer.render.call_args.kwargs["output_path"]
        self.assertEqual(called_output, Path("/tmp/result.pdf"))

    @patch("well_log_os.pipeline.MatplotlibRenderer")
    @patch("well_log_os.pipeline.build_document_for_logfile")
    @patch("well_log_os.pipeline.load_dataset_for_logfile")
    @patch("well_log_os.pipeline.load_logfile")
    def test_render_from_logfile_passes_continuous_strip_page_height(
        self,
        mock_load_logfile,
        mock_load_dataset,
        mock_build_document,
        mock_renderer_class,
    ) -> None:
        spec = LogFileSpec(
            name="test",
            data_source_path="input.las",
            data_source_format="las",
            render_backend="matplotlib",
            render_output_path="result.pdf",
            render_dpi=320,
            render_continuous_strip_page_height_mm=280.0,
            document={"name": "test"},
        )
        dataset = Mock(name="dataset")
        document = Mock(name="document")
        mock_load_logfile.return_value = spec
        mock_load_dataset.return_value = (dataset, Path("/tmp/input.las"))
        mock_build_document.return_value = document
        renderer = mock_renderer_class.return_value
        renderer.render.return_value = RenderResult(
            backend="matplotlib",
            page_count=1,
            output_path=Path("/tmp/result.pdf"),
        )

        render_from_logfile("/tmp/config.log.yaml")
        mock_renderer_class.assert_called_once_with(
            dpi=320,
            continuous_strip_page_height_mm=280.0,
        )

    @patch("well_log_os.pipeline.MatplotlibRenderer")
    @patch("well_log_os.pipeline.build_document_for_logfile")
    @patch("well_log_os.pipeline.load_dataset_for_logfile")
    @patch("well_log_os.pipeline.load_logfile")
    def test_render_from_logfile_passes_matplotlib_style(
        self,
        mock_load_logfile,
        mock_load_dataset,
        mock_build_document,
        mock_renderer_class,
    ) -> None:
        spec = LogFileSpec(
            name="test",
            data_source_path="input.las",
            data_source_format="las",
            render_backend="matplotlib",
            render_output_path="result.pdf",
            render_dpi=300,
            render_matplotlib={"style": {"track": {"x_tick_labelsize": 7.2}}},
            document={"name": "test"},
        )
        dataset = Mock(name="dataset")
        document = Mock(name="document")
        mock_load_logfile.return_value = spec
        mock_load_dataset.return_value = (dataset, Path("/tmp/input.las"))
        mock_build_document.return_value = document
        renderer = mock_renderer_class.return_value
        renderer.render.return_value = RenderResult(
            backend="matplotlib",
            page_count=1,
            output_path=Path("/tmp/result.pdf"),
        )

        render_from_logfile("/tmp/config.log.yaml")
        mock_renderer_class.assert_called_once_with(
            dpi=300,
            style={"track": {"x_tick_labelsize": 7.2}},
        )

    @patch("well_log_os.pipeline.build_document_for_logfile")
    @patch("well_log_os.pipeline.load_dataset_for_logfile")
    @patch("well_log_os.pipeline.load_logfile")
    def test_render_from_logfile_rejects_unknown_backend(
        self,
        mock_load_logfile,
        mock_load_dataset,
        mock_build_document,
    ) -> None:
        spec = LogFileSpec(
            name="test",
            data_source_path="input.las",
            data_source_format="las",
            render_backend="unknown",
            render_output_path="result.pdf",
            render_dpi=200,
            document={"name": "test"},
        )
        mock_load_logfile.return_value = spec
        mock_load_dataset.return_value = (Mock(name="dataset"), Path("/tmp/input.las"))
        mock_build_document.return_value = Mock(name="document")

        with self.assertRaises(TemplateValidationError):
            render_from_logfile("/tmp/config.log.yaml")


if __name__ == "__main__":
    unittest.main()
