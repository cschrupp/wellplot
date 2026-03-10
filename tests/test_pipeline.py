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
    @patch("well_log_os.pipeline.build_documents_for_logfile")
    @patch("well_log_os.pipeline.load_datasets_for_logfile")
    @patch("well_log_os.pipeline.load_logfile")
    def test_render_from_logfile_uses_master_matplotlib_loader(
        self,
        mock_load_logfile,
        mock_load_datasets,
        mock_build_documents,
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
        mock_load_datasets.return_value = (
            {"main": dataset},
            {"main": Path("/tmp/input.las")},
        )
        mock_build_documents.return_value = (document,)
        renderer = mock_renderer_class.return_value
        renderer.render_documents.return_value = RenderResult(
            backend="matplotlib",
            page_count=1,
            output_path=Path("/tmp/result.pdf"),
        )

        result = render_from_logfile("/tmp/config.log.yaml")
        self.assertEqual(result.backend, "matplotlib")
        mock_renderer_class.assert_called_once_with(dpi=320)
        renderer.render_documents.assert_called_once()
        called_output = renderer.render_documents.call_args.kwargs["output_path"]
        self.assertEqual(called_output, Path("/tmp/result.pdf"))

    @patch("well_log_os.pipeline.MatplotlibRenderer")
    @patch("well_log_os.pipeline.build_documents_for_logfile")
    @patch("well_log_os.pipeline.load_datasets_for_logfile")
    @patch("well_log_os.pipeline.load_logfile")
    def test_render_from_logfile_passes_continuous_strip_page_height(
        self,
        mock_load_logfile,
        mock_load_datasets,
        mock_build_documents,
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
        mock_load_datasets.return_value = (
            {"main": dataset},
            {"main": Path("/tmp/input.las")},
        )
        mock_build_documents.return_value = (document,)
        renderer = mock_renderer_class.return_value
        renderer.render_documents.return_value = RenderResult(
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
    @patch("well_log_os.pipeline.build_documents_for_logfile")
    @patch("well_log_os.pipeline.load_datasets_for_logfile")
    @patch("well_log_os.pipeline.load_logfile")
    def test_render_from_logfile_passes_matplotlib_style(
        self,
        mock_load_logfile,
        mock_load_datasets,
        mock_build_documents,
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
        mock_load_datasets.return_value = (
            {"main": dataset},
            {"main": Path("/tmp/input.las")},
        )
        mock_build_documents.return_value = (document,)
        renderer = mock_renderer_class.return_value
        renderer.render_documents.return_value = RenderResult(
            backend="matplotlib",
            page_count=1,
            output_path=Path("/tmp/result.pdf"),
        )

        render_from_logfile("/tmp/config.log.yaml")
        mock_renderer_class.assert_called_once_with(
            dpi=300,
            style={"track": {"x_tick_labelsize": 7.2}},
        )

    @patch("well_log_os.pipeline.build_documents_for_logfile")
    @patch("well_log_os.pipeline.load_datasets_for_logfile")
    @patch("well_log_os.pipeline.load_logfile")
    def test_render_from_logfile_rejects_unknown_backend(
        self,
        mock_load_logfile,
        mock_load_datasets,
        mock_build_documents,
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
        mock_load_datasets.return_value = (
            {"main": Mock(name="dataset")},
            {"main": Path("/tmp/input.las")},
        )
        mock_build_documents.return_value = (Mock(name="document"),)

        with self.assertRaises(TemplateValidationError):
            render_from_logfile("/tmp/config.log.yaml")

    @patch("well_log_os.pipeline.MatplotlibRenderer")
    @patch("well_log_os.pipeline.build_documents_for_logfile")
    @patch("well_log_os.pipeline.load_datasets_for_logfile")
    @patch("well_log_os.pipeline.load_logfile")
    def test_render_from_logfile_renders_all_sections_with_matplotlib(
        self,
        mock_load_logfile,
        mock_load_datasets,
        mock_build_documents,
        mock_renderer_class,
    ) -> None:
        spec = LogFileSpec(
            name="test",
            data_source_path="input.las",
            data_source_format="las",
            render_backend="matplotlib",
            render_output_path="result.pdf",
            render_dpi=300,
            document={"name": "test"},
        )
        dataset_main = Mock(name="dataset_main")
        dataset_aux = Mock(name="dataset_aux")
        doc_main = Mock(
            name="doc_main",
            metadata={"layout_sections": {"active_section": {"id": "main"}}},
        )
        doc_aux = Mock(
            name="doc_aux",
            metadata={"layout_sections": {"active_section": {"id": "aux"}}},
        )
        mock_load_logfile.return_value = spec
        mock_load_datasets.return_value = (
            {"main": dataset_main, "aux": dataset_aux},
            {"main": Path("/tmp/input.las"), "aux": Path("/tmp/input.las")},
        )
        mock_build_documents.return_value = (doc_main, doc_aux)
        renderer = mock_renderer_class.return_value
        renderer.render_documents.return_value = RenderResult(
            backend="matplotlib",
            page_count=3,
            output_path=Path("/tmp/result.pdf"),
        )

        render_from_logfile("/tmp/config.log.yaml")
        renderer.render_documents.assert_called_once()
        called_documents = renderer.render_documents.call_args.args[0]
        called_datasets = renderer.render_documents.call_args.args[1]
        self.assertEqual(called_documents, (doc_main, doc_aux))
        self.assertEqual(called_datasets, (dataset_main, dataset_aux))

    @patch("well_log_os.pipeline.build_documents_for_logfile")
    @patch("well_log_os.pipeline.load_datasets_for_logfile")
    @patch("well_log_os.pipeline.load_logfile")
    def test_render_from_logfile_rejects_multisection_plotly(
        self,
        mock_load_logfile,
        mock_load_datasets,
        mock_build_documents,
    ) -> None:
        spec = LogFileSpec(
            name="test",
            data_source_path="input.las",
            data_source_format="las",
            render_backend="plotly",
            render_output_path="result.html",
            render_dpi=200,
            document={"name": "test"},
        )
        mock_load_logfile.return_value = spec
        mock_load_datasets.return_value = (
            {"main": Mock(name="dataset"), "aux": Mock(name="dataset")},
            {"main": Path("/tmp/input.las"), "aux": Path("/tmp/input.las")},
        )
        mock_build_documents.return_value = (Mock(name="document_1"), Mock(name="document_2"))

        with self.assertRaises(TemplateValidationError):
            render_from_logfile("/tmp/config.log.yaml")


if __name__ == "__main__":
    unittest.main()
