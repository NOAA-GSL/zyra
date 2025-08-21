from zyra import connectors, processing, utils, visualization


def test_import_processing_package_without_viz():
    # smoke-import modules, ensures packaging and optional deps don't break import
    assert hasattr(connectors, "S3Connector")
    assert hasattr(processing, "VideoProcessor")
    assert hasattr(visualization, "PlotManager")
    assert hasattr(utils, "DateManager")
