# encoding: UTF-8
"""
单标的海龟交易策略，实现了完整海龟策略中的信号部分。
"""
from __future__ import division
from vnpy.app.cta_strategy.ctaTemplatePatch import CtaTemplatePatch
from vnpy.app.cta_strategy import (
    BarData,
    TickData,
    BarGenerator,
    ArrayManager,
)
from vnpy.app.cta_strategy.base import Direction
import talib


########################################################################
class TurtleTradingStrategy(CtaTemplatePatch):
    """海龟交易策略"""
    className = 'TurtleTradingStrategy'
    author = u'用Python的交易员'
    # 策略参数
    entryWindow = 55  # 入场通道窗口
    exitWindow = 20  # 出场通道窗口
    atrWindow = 20  # 计算ATR波动率的窗口

    # 策略变量
    entryUp = 0  # 入场通道上轨
    entryDown = 0  # 入场通道下轨
    exitUp = 0  # 出场通道上轨
    exitDown = 0  # 出场通道下轨
    atrVolatility = 0  # ATR波动率

    longEntry = 0  # 多头入场价格
    shortEntry = 0  # 空头入场价格
    longStop = 0  # 多头止损价格
    shortStop = 0  # 空头止损价格

    # 参数列表，保存了参数的名称
    parameters = CtaTemplatePatch.parameters + [
        'entryWindow', 'exitWindow', 'atrWindow'
    ]
    # 变量列表，保存了变量的名称
    varList = CtaTemplatePatch.varList + [
        'entryUp', 'entryDown', 'exitUp', 'exitDown', 'longEntry',
        'shortEntry', 'longStop', 'shortStop', 'atrVolatility'
    ]

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['pos']

    #----------------------------------------------------------------------
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        # 注意策略类中的可变对象属性（通常是list和dict等），在策略初始化时需要重新创建，
        # 否则会出现多个策略实例之间数据共享的情况，有可能导致潜在的策略逻辑错误风险，
        # 策略类中的这些可变对象属性可以选择不写，全都放在__init__下面，写主要是为了阅读
        # 策略时方便（更多是个编程习惯的选择）

    #----------------------------------------------------------------------
    def on_bar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        super(TurtleTradingStrategy, self).on_bar(bar)

        if not self.trading:
            return

        self.cancel_all()

        # 计算指标数值
        if not self.pos:
            self.entryUp, self.entryDown = self.am.donchian(self.entryWindow)

        self.exitUp, self.exitDown = self.am.donchian(self.exitWindow)

        # 避免重启策略引发的 atrVolatility没有值的情况
        if not self.atrVolatility:
            self.atrVolatility = self.am.atr(self.atrWindow)

        # 判断是否要进行交易
        if not self.pos:
            self.atrVolatility = self.am.atr(self.atrWindow)
            self.longEntry = 0
            self.shortEntry = 0
            self.longStop = 0
            self.shortStop = 0

            self.sendBuyOrders(self.entryUp)
            self.sendShortOrders(self.entryDown)

        elif self.pos > 0:
            # 加仓逻辑
            self.sendBuyOrders(self.entryUp)

            # 止损逻辑
            sellPrice = max(self.longStop, self.exitDown)
            self.sell(sellPrice, abs(self.pos), True)

        elif self.pos < 0:
            # 加仓逻辑
            self.sendShortOrders(self.entryDown)

            # 止损逻辑
            coverPrice = min(self.shortStop, self.exitUp)
            self.cover(coverPrice, abs(self.pos), True)

        # # 同步数据到数据库
        # self.saveSyncData()

        # # 发出状态更新事件
        # self.putEvent()

    #----------------------------------------------------------------------
    def on_trade(self, trade):
        """成交推送"""
        super(TurtleTradingStrategy, self).on_trade(trade)

        if trade.direction == Direction.LONG:
            self.longEntry = trade.price
            self.longStop = self.longEntry - self.atrVolatility * 2
        else:
            self.shortEntry = trade.price
            self.shortStop = self.shortEntry + self.atrVolatility * 2

        # 发出状态更新事件
        self.putEvent()

    #----------------------------------------------------------------------
    def sendBuyOrders(self, price):
        """发出一系列的买入停止单"""
        t = self.pos / self.fixedSize

        if t < 1:
            self.buy(price, self.fixedSize, True)

        if t < 2:
            self.buy(price + self.atrVolatility * 0.5, self.fixedSize, True)

        if t < 3:
            self.buy(price + self.atrVolatility, self.fixedSize, True)

        if t < 4:
            self.buy(price + self.atrVolatility * 1.5, self.fixedSize, True)

    #----------------------------------------------------------------------
    def sendShortOrders(self, price):
        """"""
        t = self.pos / self.fixedSize

        if t > -1:
            self.short(price, self.fixedSize, True)

        if t > -2:
            self.short(price - self.atrVolatility * 0.5, self.fixedSize, True)

        if t > -3:
            self.short(price - self.atrVolatility, self.fixedSize, True)

        if t > -4:
            self.short(price - self.atrVolatility * 1.5, self.fixedSize, True)
