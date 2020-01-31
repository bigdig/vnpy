# encoding: UTF-8
""" 
加入锁仓通知功能 '0_' + self.vt_symbol + '_HedgePosition'
"""
from __future__ import division
from .ctaTemplate_6 import CtaTemplate_6
########################################################################
class CtaTemplate_7(CtaTemplate_6):

    className = 'CtaTemplate_7'
    author = u'Port'

    #----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(CtaTemplate_7, self).__init__(ctaEngine, setting)

        # 注意策略类中的可变对象属性（通常是list和dict等），在策略初始化时需要重新创建，
        # 否则会出现多个策略实例之间数据共享的情况，有可能导致潜在的策略逻辑错误风险，
        # 策略类中的这些可变对象属性可以选择不写，全都放在__init__下面，写主要是为了阅读
        # 策略时方便（更多是个编程习惯的选择）

    #----------------------------------------------------------------------
    def on_start(self):
        """启动策略（必须由用户继承实现）"""
        super(CtaTemplate_7, self).on_start()

    #----------------------------------------------------------------------
    def on_trade(self, trade: TradeData):
        """收到交易信息"""
        super(CtaTemplate_7, self).on_trade(trade)

        hedgeStratege = None
        name = '0_' + self.vt_symbol + '_HedgePosition'
        if name == self.name:
            return

        if name in self.cta_engine.strategyDict:
            hedgeStratege = self.cta_engine.strategyDict[name]
        else:
            self.write_log(u'策略 %s 没找到' % name)

        if hedgeStratege and callable(getattr(hedgeStratege, "proxyHedgeTrade", None)):
            # 方向
            hedgeStratege.proxyHedgeTrade(self.name, self.pos, self.openPrice)
