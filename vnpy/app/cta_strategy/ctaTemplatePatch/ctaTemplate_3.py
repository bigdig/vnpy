# encoding: UTF-8
'''
本文件包含了CTA引擎中的策略开发用模板。
添加了一些基本的策略属性，变量。不做下单逻辑
'''
from .ctaTemplate_2 import CtaTemplate_2
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
class CtaTemplate_3(CtaTemplate_2):
    """
    add pos fixsize
    """

    className = 'CtaTemplate_3'
    author = u'rxg'

    # 基本变量
    _fixedSize = 1  # 每次交易的数量
    posMultiper = 1  # 仓位倍率
    _pos = 0  #仓位信息

    holdTime = 0  #持仓时间
    holidayTime = 0  #休息时间
    tradeIndex = 0  #交易编号

    parameters = CtaTemplate_2.parameters + ['posMultiper','fixedSize']

    varList = CtaTemplate_2.variables + \
                [
                'holdTime',
                'holidayTime',
                'tradeIndex',
                ]

    #----------------------------------------------------------------------
    @property
    def fixedSize(self):
        """最新价格属性"""
        return abs(int(self._fixedSize * float(self.posMultiper)))

    #----------------------------------------------------------------------
    @fixedSize.setter
    def fixedSize(self, value):
        """最新价格属性"""
        self._fixedSize = value
        pass

    #----------------------------------------------------------------------
    @property
    def pos(self):
        """最新价格属性"""
        return self._pos

    #----------------------------------------------------------------------
    @pos.setter
    def pos(self, value):
        """最新价格属性"""
        if abs(self.pos):
            if value == 0 or value * self._pos < 0:
                self.holidayTime = 0  #重置空仓时间
                self.holdTime = 0
                self.tradeIndex += 1  #设置下次交易编号

        self._pos = value

    #----------------------------------------------------------------------
    @property
    def direction(self):
        """持仓方向"""
        if self.pos > 0:
            return 1

        if self.pos < 0:
            return -1

        if self.pos == 0:
            return 0

    #----------------------------------------------------------------------
    def on_bar(self, bar):
        '''处理分钟数据'''
        super().on_bar(bar)
        #计算持仓时间、休息时间
        if self.trading:
            if self.pos == 0:
                self.holidayTime += 1
            else:
                self.holdTime += 1