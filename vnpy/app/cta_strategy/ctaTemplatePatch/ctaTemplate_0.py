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
            return self.lastTick.lastPrice
        if self.lastBar:
            return self.lastBar.close

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