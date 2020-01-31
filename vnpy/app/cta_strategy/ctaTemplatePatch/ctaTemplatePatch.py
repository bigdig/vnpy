# encoding: UTF-8
'''
本文件包含了CTA引擎中的策略开发用模板。
添加了一些基本的策略属性，变量。不做下单逻辑
'''

from vnpy.trader.constant import Direction, Status, Offset, Interval
from vnpy.app.cta_strategy.base import EngineType
from .ctaTemplate_6 import CtaTemplate_6

########################################################################
class CtaTemplatePatch(CtaTemplate_6):
    """
    add trade
    """

    className = 'CtaTemplatePatch'
    author = u'rxg'

    debugMode = False
    enableManualTrade = True  # 允许手动平仓

    parameters = CtaTemplate_6.parameters + \
                [
                 'enableManualTrade','debugMode'
                 ]

    varList = CtaTemplate_6.variables + \
                [
                ]

    #----------------------------------------------------------------------
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

    #-----------------------------------------------------------------
    def clearOrder(self):
        """清仓
        """
        self.cancel_all()
        if abs(self.pos):
            self.reissue_order(-self.pos,self.tickAdd)
            self.tradeIndex += 1  #平仓后，交易编号加一

    #----------------------------------------------------------------------
    def on_trade(self, trade):
        """收到交易信息"""
        super(CtaTemplatePatch, self).on_trade(trade)

        if self.debugMode:
            #save trade
            if self.get_engine_type() == EngineType.BACKTESTING:
                trade.name = self.strategy_name  # 添加策略名TAG
                trade.datetime = str(self.lastDatetime)
                trade.dt = self.lastDatetime

    #-----------------------------------------------------------------
    def trade(self, posChange, posChange1=0):
        """
        交易指定仓位
        """
        # 检查之前委托都已结束
        if self.uncompletedOrders:
            self.write_log(
                u'委托单没有完全结束，不执行新定单 %s' % str(self.uncompletedOrders))
            return

        self.cancel_all()
        
        # 如为0不进行任何操作
        if abs(posChange):
            self.reissue_order(posChange, -self.priceTick)

        if abs(posChange1):
            self.reissue_order(posChange1, -self.priceTick)
