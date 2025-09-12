# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from zyra.connectors.discovery.ogc import OGCWMSBackend

SAMPLE_WMS = """
<WMS_Capabilities version="1.3.0" xmlns:xlink="http://www.w3.org/1999/xlink">
  <Service>
    <Name>WMS</Name>
  </Service>
  <Capability>
    <Request>
      <GetMap>
        <Format>image/png</Format>
        <DCPType>
          <HTTP>
            <Get>
              <OnlineResource xlink:href="https://example.com/wms" />
            </Get>
          </HTTP>
        </DCPType>
      </GetMap>
    </Request>
    <Layer>
      <Title>Root</Title>
      <Layer>
        <Name>global_temp</Name>
        <Title>Global Temperature</Title>
        <Abstract>Monthly mean temperature dataset</Abstract>
      </Layer>
      <Layer>
        <Name>precip</Name>
        <Title>Global Precipitation</Title>
        <Abstract>Accumulated precipitation</Abstract>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>
"""


def test_ogc_wms_search_matches_title_and_abstract():
    b = OGCWMSBackend(
        endpoint="https://example.com/wms?service=WMS&request=GetCapabilities",
        capabilities_xml=SAMPLE_WMS,
    )
    items = b.search("temperature", limit=5)
    assert any("Temperature" in d.name for d in items)
    assert all(d.source == "ogc-wms" and d.format == "WMS" for d in items)
    # Ensure base URI used from capabilities
    assert all(d.uri == "https://example.com/wms" for d in items)
