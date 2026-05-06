import pandas as pd

from valuescope.legacy_stock_scripts.core.data_a import fetch_cashflow_extras


def test_fetch_cashflow_extras_extracts_reported_operating_cashflow():
    cf = pd.DataFrame(
        [
            {
                "报告日": "20241231",
                "经营活动产生的现金流量净额": 123.0,
                "购建固定资产、无形资产和其他长期资产支付的现金": -45.0,
            }
        ]
    )

    result = fetch_cashflow_extras("000001", cf)

    assert result.loc[0, "ocf"] == 123.0


def test_fetch_cashflow_extras_derives_ocf_from_operating_inflow_and_outflow_when_net_missing():
    cf = pd.DataFrame(
        [
            {
                "报告日": "20241231",
                "经营活动现金流入小计": 500.0,
                "经营活动现金流出小计": 320.0,
            }
        ]
    )

    result = fetch_cashflow_extras("000001", cf)

    assert result.loc[0, "ocf"] == 180.0
