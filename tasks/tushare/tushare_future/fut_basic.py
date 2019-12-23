"""
Created on 2018/11/20
@author: yby
@desc    : 2018-11-20
contact author:ybychem@gmail.com
"""

import logging
from datetime import datetime, timedelta

from ibats_utils.mess import STR_FORMAT_DATE, try_n_times
from sqlalchemy.dialects.mysql import DOUBLE
from sqlalchemy.types import String, Date, Text

from tasks import app
from tasks.backend import engine_md, bunch_insert
from tasks.tushare.ts_pro_api import pro

DEBUG = False
logger = logging.getLogger()
DATE_BASE = datetime.strptime('2005-01-01', STR_FORMAT_DATE).date()
ONE_DAY = timedelta(days=1)
# 标示每天几点以后下载当日行情数据
BASE_LINE_HOUR = 16
STR_FORMAT_DATE_TS = '%Y%m%d'

INDICATOR_PARAM_LIST_TUSHARE_FUTURE_BASIC = [
    ('ts_code', String(20)),
    ('symbol', String(20)),
    ('exchange', String(20)),
    ('name', String(20)),
    ('fut_code', String(20)),
    ('trade_unit', String(20)),
    ('per_unit', DOUBLE),
    ('quote_unit', String(100)),
    ('quote_unit_desc', String(100)),
    ('d_mode_desc', Text),
    ('list_date', Date),
    ('delist_date', Date),
    ('d_month', String(20)),
    ('last_ddate', Date),
    ('trade_time_desc', Text),
]
# 设置 dtype
DTYPE_TUSHARE_FUTURE_BASIC = {key: val for key, val in INDICATOR_PARAM_LIST_TUSHARE_FUTURE_BASIC}

df = pro.fut_basic(exchange='DCE')


@try_n_times(times=3, sleep_time=6)
def invoke_fut_basic(exchange):
    invoke_fut_basic = pro.fut_basic(exchange=exchange)
    return invoke_fut_basic


@app.task
def import_fut_basic(chain_param=None):
    """
    插入股票日线数据到最近一个工作日-1。
    如果超过 BASE_LINE_HOUR 时间，则获取当日的数据
    :return:
    """
    table_name = 'tushare_future_basic'
    logging.info("更新 %s 开始", table_name)

    has_table = engine_md.has_table(table_name)
    exchange_list = ['DCE', 'CZCE', 'SHFE', 'CFFEX', 'INE']

    try:
        for i in range(len(exchange_list)):
            exchange_name = exchange_list[i]
            data_df = invoke_fut_basic(exchange=exchange_name)
            if len(data_df) > 0:
                data_count = bunch_insert(data_df, table_name=table_name,
                                          dtype=DTYPE_TUSHARE_FUTURE_BASIC, primary_keys=['ts_code'])
                logging.info("更新 %s 期货合约基础信息结束， %d 条信息被更新", exchange_name, data_count)
            else:
                logging.info("无数据信息可被更新")
    finally:

        logger.info('%s 表 数据更新完成', table_name)


if __name__ == "__main__":
    # DEBUG = True
    import_fut_basic()
