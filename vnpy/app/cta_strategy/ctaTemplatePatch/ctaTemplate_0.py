# encoding: UTF-8
'''
本文件包含了CTA引擎中的策略开发用模板。
添加了一些基本的策略属性，变量。不做下单逻辑
'''

from vnpy.app.cta_strategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)
from datetime import datetime

########################################################################
class CtaTemplate_0(CtaTemplate):
    """
    Add lastTick lastBar
    """
    #基本变量
    lastTick = None         # 最新tick数据
    lastBar = None          # 最新bar数据

    # 参数列表，保存了参数的名称
    parameters = CtaTemplate.parameters + []

    # 变量列表，保存了变量的名称
    varList = CtaTemplate.variables + ['lastPrice']

    #----------------------------------------------------------------------
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)


    def update_setting(self, setting: dict):
        """
        Update strategy parameter wtih value in setting dict.
        """
        # 设置策略的参数
        for key in self.parameters:
            if key in setting:
                #d[key] = setting[key]
                tp = type(getattr(self, key))
                
                #buf-fix settingFile may be string or list
                if key != 'settingFile' and tp:

                    if tp in [int,float,bool]:
                        setattr(self, key, eval(str(setting[key])) )
                    else:
                        setattr(self, key, tp(setting[key]) )
                else:
                    setattr(self, key, setting[key])

    #----------------------------------------------------------------------
    def on_tick(self, tick):
        """收到行情推送"""
        self.lastTick = tick
        
    #----------------------------------------------------------------------
    def on_bar(self, bar):
        """收到K线推送"""
        self.lastBar = bar

    #----------------------------------------------------------------------
    @property
    def lastPrice(self):
        """最新价格属性"""
        if self.lastTick:
            return self.lastTick.last_price
        if self.lastBar:
            return self.lastBar.close_price

        return 0
        pass

    #----------------------------------------------------------------------
    @lastPrice.setter
    def lastPrice(self, value):
        """最新价格属性"""
        pass

    #----------------------------------------------------------------------
    @property
    def lastDatetime(self):
        """最新价格属性"""
        if self.lastTick:
            return self.lastTick.datetime
        if self.lastBar:
            return self.lastBar.datetime

        return datetime(1, 1, 1)
        pass

    #----------------------------------------------------------------------
    @lastDatetime.setter
    def lastDatetime(self, value):
        """最新价格属性"""
        pass