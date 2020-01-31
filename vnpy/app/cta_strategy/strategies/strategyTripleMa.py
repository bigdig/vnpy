  # encoding: UTF-8

"""
TripleMAStrategy
基于三均线的交易策略 (m2 m3 设置止损线，ATR斜率低时加仓)
"""

# 首先写系统内置模块
from __future__ import division
from vnpy.app.cta_strategy import (
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)
from vnpy.app.cta_strategy.ctaTemplatePatch import CtaTemplatePatch
from .TripleMaSignal import TripleMaSignal

########################################################################
class TripleMAStrategy(CtaTemplatePatch):
    """基于三均线的交易策略"""
    className = 'TripleMAStrategy'
    author = 'renxg'

    # ----------------------------------------------------------------------
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        # 跳期交易
        self.signal = TripleMaSignal(self,self.kLineCycle//2)  # 30分钟
        self.stopOrderList = []

    #----------------------------------------------------------------------
    def on_bar(self, bar):
        """K线更新"""
        self.signal.onBar(bar)
        super().on_bar(bar)

    #----------------------------------------------------------------------
    def onXminBar(self, bar):
        """收到X分钟K线"""
        super(TripleMAStrategy, self).onXminBar(bar)

        if not self.trading:
            return
        if not self.am.inited:
            return
            
        # 发出状态更新事件
        if self.trading:

            self.cancel_all()

            direction = self.signal.get_signal_pos()

            if self.pos == 0:
                #空仓，开新仓
                self.filterTrade(direction)
            else:
                #持仓相反，平仓 （没有方向时不平仓）
                if self.direction * direction < 0:
                    self.clearOrder()
                else:
                    # 方向不在时，设置止损点位
                    if not self.direction == direction:
                        self.setStopOrder(self.signal.ma3,self.pos)

                    # 设置加仓
                    if self.direction == 1:
                        self.sendBuyOrders()
                    else:
                        self.sendShortOrders()

    #----------------------------------------------------------------------
    def filterTrade(self,direction):
        """按规则过滤交易"""
        
        if direction == 0:
            return

        # 太小容易止损，反复
        if abs(self.lastPrice - self.signal.ma3) < self.getVolatility() * self.lastPrice:
            return

        self.trade( self.fixedSize * direction)
        self.put_event()
        
    #----------------------------------------------------------------------
    def setStopOrder(self,price, pos):
        """移动止损"""
        if abs(self.pos) == 0:
            return

        if self.trading:
            #如果已经设置移动止损单，撤消
            for orderID in self.stopOrderList:
                self.cancel_order(orderID)
            self.stopOrderList = []

            # 持有多头仓位
            if self.direction > 0:
                # 发出本地止损委托，并且把委托号记录下来，用于后续撤单
                self.stopOrderList = self.sell(price, abs(pos), stop=True)
            # 持有空头仓位
            elif self.direction < 0:
                # 计算空头移动止损
                self.stopOrderList = self.cover(price, abs(pos), stop=True)

    #----------------------------------------------------------------------
    def sendBuyOrders(self):
        """发出一系列的买入停止单"""
        t = self.pos / self.fixedSize

        volatility = self.getVolatility()

        if t < 1:
            return

        if t < 2:
            self.buy(self.openPrice*(1 + volatility), self.fixedSize, True)
            return

        if t < 3:
            self.buy(self.openPrice*(1 + 1.5*volatility), self.fixedSize, True)
            return

        if t < 4:
            self.buy(self.openPrice*(1 + 2.0*volatility), self.fixedSize, True)
            return

    #----------------------------------------------------------------------
    def sendShortOrders(self):
        """"""
        t = self.pos / self.fixedSize

        volatility = self.getVolatility()

        if t > -1:
            return

        if t > -2:
            self.short(self.openPrice*(1 - volatility), self.fixedSize, True)
            return

        if t > -3:
            self.short(self.openPrice*(1 - 1.5*volatility), self.fixedSize, True)
            return

        if t > -4:
            self.short(self.openPrice*(1 - 2.0*volatility), self.fixedSize, True)
            return