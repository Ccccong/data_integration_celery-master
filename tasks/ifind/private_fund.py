# -*- coding: utf-8 -*-
"""
Created on 2018/1/17
@author: MG
@desc    : 2018-08-29 已经正式运行测试完成，可以正常使用
"""

import logging
from datetime import date, datetime, timedelta
import pandas as pd
from tasks.backend.orm import build_primary_key
from tasks.ifind import invoker
from ibats_utils.mess import STR_FORMAT_DATE
from sqlalchemy.types import String, Date, Integer, Boolean
from sqlalchemy.dialects.mysql import DOUBLE
from ibats_utils.mess import unzip_join
from ibats_utils.db import with_db_session, alter_table_2_myisam, bunch_insert_on_duplicate_update
from tasks.backend import engine_md
from tasks import app
from tasks.merge.code_mapping import update_from_info_table

TRIAL = True
DEBUG = False
logger = logging.getLogger()
DATE_BASE = datetime.strptime('1990-01-01', STR_FORMAT_DATE).date()
ONE_DAY = timedelta(days=1)
# 标示每天几点以后下载当日行情数据
BASE_LINE_HOUR = 20


def get_private_fund_set(date_fetch, field='051010001'):
    """
    获取基金代码表
    :param date_fetch:
    :param field:
    阳光私募类-全部(已成立、未到期):051010001
    阳光私募类-已到期(阳光私募):051010005
    :return:
    """
    date_fetch_str = date_fetch.strftime(STR_FORMAT_DATE)
    # TODO: 增加对已到期基金的信息更新
    # 全部私募基金 051010001 仅用测试使用的小数据集（051010020005002）
    # 阳光私募类-全部(已成立、未到期):051010001
    # 阳光私募类-已到期(阳光私募):051010005
    fund_df = invoker.THS_DataPool('block', date_fetch_str + ';' + field, 'date:Y,thscode:Y,security_name:Y')
    if fund_df is None:
        logging.warning('%s 获取基金代码失败', date_fetch_str)
        return None
    fund_count = fund_df.shape[0]
    logging.info('get %d private fund on %s of %s', fund_count, date_fetch_str, field)
    return set(fund_df['THSCODE'])


@app.task
def import_private_fund_info(chain_param=None, ths_code=None, refresh=False):
    """
    更新基础信息表
    :param chain_param: 该参数仅用于 task.chain 串行操作时，上下传递参数使用
    :param ths_code:
    :param refresh:
    :return:
    """
    table_name = 'ifind_private_fund_info'
    has_table = engine_md.has_table(table_name)
    logging.info("更新 %s 开始", table_name)
    if ths_code is None:
        # 获取全市场私募基金代码及名称

        date_end = date.today()
        private_fund_set = set()

        if not refresh and has_table:
            sql_str = "select ths_code, ths_maturity_date_sp from {table_name}".format(table_name=table_name)
            with with_db_session(engine_md) as session:
                code_in_db_dict = dict(session.execute(sql_str).fetchall())
                code_in_db_set = set(code_in_db_dict.keys())
        else:
            code_in_db_dict, code_in_db_set = {}, set()

        # 查找新增基金
        code_set_exists = get_private_fund_set(date_end)
        if code_set_exists is not None:
            if not refresh and has_table:
                code_set_exists -= code_in_db_set
            private_fund_set |= code_set_exists

        # 查找已清盘基金
        code_set_clear = get_private_fund_set(date_end, field='051010005')
        if code_set_clear is not None:
            if not refresh and has_table:
                code_set_clear -= set([key for key, val in code_in_db_dict.items() if val is not None])
            private_fund_set |= code_set_clear

        ths_code = list(private_fund_set)
        if DEBUG:
            ths_code = ths_code[:10]

    indicator_param_list = [
        ('ths_product_short_name_sp', '', String(80)),
        ('ths_product_full_name_sp', '', String(80)),
        ('ths_trust_category_sp', '', String(40)),
        ('ths_is_structured_product_sp', '', String(10)),
        ('ths_threshold_amt_sp', '', Integer),
        ('ths_low_add_amt_sp', '', Integer),
        ('ths_fore_max_issue_scale_sp', '', String(40)),
        ('ths_actual_issue_scale_sp', '', String(40)),
        ('ths_invest_manager_current_sp', '', String(60)),
        ('ths_mendator_sp', '', String(20)),
        ('ths_recommend_sd_sp', '', Date),
        ('ths_introduction_ed_sp', '', Date),
        ('ths_established_date_sp', '', Date),
        ('ths_maturity_date_sp', '', Date),
        ('ths_found_years_sp', '', Date),
        ('ths_duration_y_sp', '', Integer),
        ('ths_remain_duration_d_sp', '', Integer),
        ('ths_float_manage_rate_sp', '', DOUBLE),
        ('ths_mandate_fee_rate_sp', '', DOUBLE),
        ('ths_subscription_rate_explain_sp', '', String(300)),
        ('ths_redemp_rate_explain_sp', '', String(300)),
        ('ths_opening_period_explain_sp', '', String(300)),
        ('ths_close_period_explain_sp', '', String(300)),
        ('ths_trustee_sp', '', String(100)),
        ('ths_secbroker_sp', '', String(40))
    ]
    # jsonIndicator='THS_BasicData('SM000008.XT','ths_product_short_name_sp;ths_product_full_name_sp;ths_trust_category_sp;ths_is_structured_product_sp;ths_threshold_amt_sp;ths_low_add_amt_sp;ths_fore_max_issue_scale_sp;ths_actual_issue_scale_sp;ths_invest_manager_current_sp;ths_invest_advisor_sp;ths_mendator_sp;ths_recommend_sd_sp;ths_introduction_ed_sp;ths_established_date_sp;ths_maturity_date_sp;ths_found_years_sp;ths_duration_y_sp;ths_remain_duration_d_sp;ths_float_manage_rate_sp;ths_mandate_fee_rate_sp;ths_subscription_rate_explain_sp;ths_redemp_rate_explain_sp;ths_opening_period_explain_sp;ths_close_period_explain_sp;ths_trustee_sp;ths_secbroker_sp'
    # jsonparam=';;;;;;;;;'
    indicator, param = unzip_join([(key, val) for key, val, _ in indicator_param_list], sep=';')
    data_df = invoker.THS_BasicData(ths_code, indicator, param, max_code_num=8000)
    if data_df is None or data_df.shape[0] == 0:
        logging.info("没有可用的数据可以更新")
        return

    dtype = {key: val for key, _, val in indicator_param_list}
    dtype['ths_code'] = String(20)
    data_count = bunch_insert_on_duplicate_update(data_df, table_name, engine_md, dtype)
    logging.info("更新 %s 完成 存量数据 %d 条", table_name, data_count)
    if not has_table:
        alter_table_2_myisam(engine_md, [table_name])
        build_primary_key([table_name])

    # 更新 code_mapping 表
    update_from_info_table(table_name)


@app.task
def import_private_fund_daily(chain_param=None, ths_code_set: set = None, begin_time=None):
    """
    导入 daily 数据
    :param chain_param: 该参数仅用于 task.chain 串行操作时，上下传递参数使用
    :param ths_code_set:
    :param begin_time:
    :return:
    """
    table_name = 'ifind_private_fund_daily'
    indicator_param_list = [
        ('netAssetValue', '', DOUBLE),
        ('adjustedNAV', '', DOUBLE),
        ('accumulatedNAV', '', DOUBLE),
        ('premium', '', DOUBLE),
        ('premiumRatio', '', DOUBLE),
        ('estimatedPosition', '', DOUBLE)
    ]
    # jsonIndicator='netAssetValue，adjustedNAV，accumulatedNAV，premium，premiumRatio，estimatedPosition'
    # jsonparam=';;;;'
    json_indicator, json_param = unzip_join([(key, val) for key, val, _ in indicator_param_list], sep=';')
    has_table = engine_md.has_table(table_name)
    if has_table:
        sql_str = """SELECT ths_code, date_frm, if(ths_maturity_date_sp<end_date, ths_maturity_date_sp, end_date) date_to
            FROM
            (
                SELECT info.ths_code, ifnull(trade_date_max_1, ths_established_date_sp) date_frm, ths_maturity_date_sp,
                if(hour(now())<16, subdate(curdate(),1), curdate()) end_date
                FROM 
                    ifind_private_fund_info info 
                LEFT OUTER JOIN
                    (SELECT ths_code, adddate(max(time),1) trade_date_max_1 FROM {table_name} GROUP BY ths_code) daily
                ON info.ths_code = daily.ths_code
            ) tt
            WHERE date_frm <= if(ths_maturity_date_sp<end_date, ths_maturity_date_sp, end_date) 
            ORDER BY ths_code""".format(table_name=table_name)
    else:
        logger.warning('ifind_private_fund_daily 不存在，仅使用 ifind_private_fund_info 表进行计算日期范围')
        sql_str = """SELECT ths_code, date_frm, if(ths_maturity_date_sp<end_date, ths_maturity_date_sp, end_date) date_to
            FROM
            (
                SELECT info.ths_code, ths_established_date_sp date_frm, ths_maturity_date_sp,
                if(hour(now())<16, subdate(curdate(),1), curdate()) end_date
                FROM ifind_private_fund_info info 
            ) tt
            WHERE date_frm <= if(ths_maturity_date_sp<end_date, ths_maturity_date_sp, end_date) 
            ORDER BY ths_code"""

    with with_db_session(engine_md) as session:
        # 计算每只股票需要获取日线数据的日期区间
        table = session.execute(sql_str)
        code_date_range_dic = {
            ths_code: (date_from if begin_time is None else min([date_from, begin_time]), date_to)
            for ths_code, date_from, date_to in table.fetchall() if
            ths_code_set is None or ths_code in ths_code_set}

    if TRIAL:
        date_from_min = date.today() - timedelta(days=(365 * 5))
        # 试用账号只能获取近5年数据
        code_date_range_dic = {
            ths_code: (max([date_from, date_from_min]), date_to)
            for ths_code, (date_from, date_to) in code_date_range_dic.items() if date_from_min <= date_to}

    # 设置 dtype
    dtype = {key: val for key, _, val in indicator_param_list}
    dtype['ths_code'] = String(20)
    dtype['time'] = Date

    data_df_list, data_count, tot_data_count, code_count = [], 0, 0, len(code_date_range_dic)
    try:
        for num, (ths_code, (begin_time, end_time)) in enumerate(code_date_range_dic.items(), start=1):
            logger.debug('%d/%d) %s [%s - %s]', num, code_count, ths_code, begin_time, end_time)
            data_df = invoker.THS_HistoryQuotes(
                ths_code,
                json_indicator,
                json_param,
                begin_time, end_time
            )
            if data_df is not None and data_df.shape[0] > 0:
                data_count += data_df.shape[0]
                data_df_list.append(data_df)
            # 大于阀值有开始插入
            if data_count >= 10000:
                tot_data_df = pd.concat(data_df_list)
                # tot_data_df.to_sql(table_name, engine_md, if_exists='append', index=False, dtype=dtype)
                data_count = bunch_insert_on_duplicate_update(tot_data_df, table_name, engine_md, dtype)
                tot_data_count += data_count
                data_df_list, data_count = [], 0

            if DEBUG and len(data_df_list) > 1:
                break
    finally:
        if data_count > 0:
            tot_data_df = pd.concat(data_df_list)
            # tot_data_df.to_sql(table_name, engine_md, if_exists='append', index=False, dtype=dtype)
            data_count = bunch_insert_on_duplicate_update(tot_data_df, table_name, engine_md, dtype)
            tot_data_count += data_count

        logging.info("更新 %s 完成 新增数据 %d 条", table_name, tot_data_count)
        if not has_table:
            alter_table_2_myisam(engine_md, [table_name])
            build_primary_key([table_name])


if __name__ == "__main__":
    # DEBUG = True
    TRIAL = True
    # 基金基本信息数据加载
    # ths_code = None  # '600006.SH,600009.SH'
    # import_fund_info(None, ths_code)
    # 基金日K数据行情加载
    ths_code = None  # '600006.SH,600009.SH'
    import_private_fund_daily(None, ths_code)
