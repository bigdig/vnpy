# encoding: UTF-8
"""
移动止损策略：对从策略进行移动止损操作
请按命名规则在策略配置文件中配置
"""

from __future__ import division
from vnpy.app.cta_strategy.ctaTemplatePatch import CtaTemplatePatch
import copy


########################################################################
class TrailingStopStrategy(CtaTemplatePatch):
    """移动止损策略"""
    className = 'TrailingStopStrategy'
    author = u'renxg'

    # 止损变量
    intraTradeHigh = 0
    intraTradeLow = 0
    intraTradeHighDateTime = None
    intraTradeLowDateTime = None

    longStop = 0
    shortStop = 0
    stopOrderList = None

    exitOnTopRtnPips = 0.008
    halfTime = 60

    slaveStrategy = None
    slaveTradeIndex = 0  #区分从策略持仓，以此来感知仓位变换

    # 参数列表，保存了参数的名称
    parameters = CtaTemplatePatch.parameters + ['exitOnTopRtnPips', 'halfTime']

    # 变量列表，保存了变量的名称
    variables = CtaTemplatePatch.variables + [
        'intraTradeHigh', 'intraTradeLow', 'longStop', 'shortStop',
        'slaveTradeIndex', 'intraTradeHighDateTime', 'intraTradeLowDateTime'
    ]

    #----------------------------------------------------------------------
    # ----------------------------------------------------------------------
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.stopOrderList = []
        # self.tag = (hash(self.name) % 1e+5) * 1e-10
        # self.write_log( u'Tag: {:.10f}'.format(self.tag))

    #----------------------------------------------------------------------
    def on_start(self):
        """启动策略（必须由用户继承实现）"""
        super().on_start()

        # 重设止损单
        if self.trading:
            if self.getSlaveStrategy():
                if abs(self.slaveStrategy.pos):
                    self.setStopOrder()

    #----------------------------------------------------------------------
    def on_tick(self, tick):
        """收到行情TICK推送（必须由用户继承实现）"""
        super().on_tick(tick)

        if self.trading:
            if self.getSlaveStrategy():
                #设置从策略持有期内的最高价、最低价
                if abs(
                        self.slaveStrategy.pos
                ) and self.slaveStrategy.tradeIndex == self.slaveTradeIndex:
                    # 计算持有期内的最高价
                    self.intraTradeHigh = max(self.intraTradeHigh,
                                              tick.lastPrice)
                    self.intraTradeLow = min(self.intraTradeLow,
                                             tick.lastPrice)
                    if self.intraTradeHigh == tick.lastPrice:
                        self.intraTradeHighDateTime = tick.datetime
                    if self.intraTradeLow == tick.lastPrice:
                        self.intraTradeLowDateTime = tick.datetime
                else:
                    #重置
                    self.intraTradeHigh = tick.lastPrice
                    self.intraTradeLow = tick.lastPrice
                    self.slaveTradeIndex = self.slaveStrategy.tradeIndex
                    self.intraTradeHighDateTime = tick.datetime
                    self.intraTradeLowDateTime = tick.datetime

    #----------------------------------------------------------------------
    def on_bar(self, bar):
        '''处理分钟数据'''
        super().on_bar(bar)

        if self.trading:
            if self.getSlaveStrategy():
                #设置从策略持有期内的最高价、最低价
                if abs(
                        self.slaveStrategy.pos
                ) and self.slaveStrategy.tradeIndex == self.slaveTradeIndex:
                    # 计算持有期内的最高价
                    self.intraTradeHigh = max(self.intraTradeHigh, bar.high_price)
                    self.intraTradeLow = min(self.intraTradeLow, bar.low_price)
                    if self.intraTradeHigh == bar.high_price:
                        self.intraTradeHighDateTime = bar.datetime
                    if self.intraTradeLow == bar.low_price:
                        self.intraTradeLowDateTime = bar.datetime
                else:
                    #重置
                    self.intraTradeHigh = bar.high_price
                    self.intraTradeLow = bar.low_price
                    self.slaveTradeIndex = self.slaveStrategy.tradeIndex
                    self.intraTradeHighDateTime = bar.datetime
                    self.intraTradeLowDateTime = bar.datetime

                if abs(self.slaveStrategy.pos):
                    self.setStopOrder()

    #----------------------------------------------------------------------
    def onXminBar(self, bar):
        """收到K线推送"""
        super(TrailingStopStrategy, self).onXminBar(bar)
        if not self.trading:
            return
        if not self.am.inited:
            return

    #----------------------------------------------------------------------
    def on_stop(self):
        """停止策略（必须由用户继承实现）"""
        #如果已经设置移动止损单，撤消
        for orderID in self.stopOrderList:
            self.slaveStrategy.cancel_order(orderID)
        self.stopOrderList = []

        super().on_stop()

    #----------------------------------------------------------------------
    def getSlaveStrategy(self):
        '''取被保护策略'''
        if not self.slaveStrategy:
            lockName = self.strategy_name.split('_Cover')[0]
            if lockName in self.cta_engine.strategyDict:
                self.slaveStrategy = self.cta_engine.strategyDict[lockName]
            else:
                self.write_log(u'策略 %s 没找到' % lockName)

        return self.slaveStrategy
        pass

    #----------------------------------------------------------------------
    def setStopOrder(self):
        """移动止损"""
        pos = self.slaveStrategy.pos
        trading = self.slaveStrategy.trading
        
        if trading:

            #如果已经设置移动止损单，撤消
            for orderID in self.stopOrderList:
                self.slaveStrategy.cancel_order(orderID)
            self.stopOrderList = []

            # 跟随止损
            if self.exitOnTopRtnPips > 0:

                halfT = self.halfTime

                # 持有多头仓位
                if pos > 0:
                    if self.intraTradeHighDateTime:
                        pips = self.exitOnTopRtnPips * 0.8**(
                            (self.lastDatetime -
                             self.intraTradeHighDateTime).seconds / 60 / halfT)
                        longStop = int(self.intraTradeHigh * (1 - pips))
                    else:
                        longStop = int(
                            self.intraTradeHigh * (1 - self.exitOnTopRtnPips))

                    # 发出本地止损委托，并且把委托号记录下来，用于后续撤单
                    self.stopOrderList = self.slaveStrategy.sell(
                        longStop, abs(pos), stop=True)
                    self.longStop = longStop
                # 持有空头仓位
                elif pos < 0:
                    # 计算空头移动止损
                    if self.intraTradeLowDateTime:
                        pips = self.exitOnTopRtnPips * 0.8**(
                            (self.lastDatetime -
                             self.intraTradeLowDateTime).seconds / 60 / halfT)
                        shortStop = int(self.intraTradeLow * (1 + pips))
                    else:
                        shortStop = int(
                            self.intraTradeLow * (1 + self.exitOnTopRtnPips))

                    self.stopOrderList = self.slaveStrategy.cover(
                        shortStop, abs(pos), stop=True)
                    self.shortStop = shortStop
                else:
                    #reset stop price
                    self.longStop = 0
                    self.shortStop = 0