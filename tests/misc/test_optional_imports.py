from datavizhub import acquisition, processing, visualization, utils


def test_import_processing_package_without_viz():
    # smoke-import modules, ensures packaging and optional deps don't break import
    assert hasattr(acquisition, "S3Manager")
    assert hasattr(processing, "VideoProcessor")
    assert hasattr(visualization, "PlotManager")
    assert hasattr(utils, "DateManager")
