# encoding: UTF-8
'''
Partially Filled Orders Replacement
the unfilled part of partially filled price order will be cancelled and the remainder will be converted into a market order 
when the specified timeout is exceeded
'''

from vnpy.trader.constant import Direction, Status, Offset, Interval
from vnpy.app.cta_strategy.base import EngineType

from datetime import datetime, timedelta, date
from copy import copy
from .ctaTemplate_0 import CtaTemplate_0
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

STATUS_FINISHED = set([ Status.REJECTED, Status.CANCELLED, Status.ALLTRADED])

#-----------------------------------------------------------
class CtaTemplate_1(CtaTemplate_0):
    """
    分钟时间内限价单不成交，补单重发
    """
    className = 'CtaTemplate_1'
    author = u'port'
    barTimeInterval = 60
    tickAdd = 5     # 委托时相对基准价格的超价
    priceTick = 1.0 # 价格最小变动
    cancelSeconds = 60 # 撤单时间(秒)

    # 参数列表，保存了参数的名称
    parameters = CtaTemplate_0.parameters + ['barTimeInterval','tickAdd','priceTick','cancelSeconds']

    # 变量列表，保存了变量的名称
    varList = CtaTemplate_0.variables + ['entrust']

    #----------------------------------------------------------------------
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        # 保存委托单编号和相关委托单的字典
        # key为委托单编号
        # value为该合约相关的委托单
        self.uncompletedOrders = {}
        self.entrust = 0  # 委托状态标记 -1 1 0

    #----------------------------------------------------------------------
    def on_order(self, order:OrderData):
        """报单更新"""
        # super(CtaTemplate_1, self).onOrder(order)

        self.write_log(
            u'OnOrder()报单更新，orderID:{0},{1},totalVol:{2},tradedVol:{3},offset:{4},price:{5},direction:{6},status:{7}'
            .format(order.orderid, order.vt_symbol, order.volume,
                    order.traded, order.offset, order.price,
                    order.direction, order.status))

        orderkey = order.vt_orderid

        if orderkey in self.uncompletedOrders:
            orderInfo = self.uncompletedOrders[orderkey]
        else:
            return

        if order.status in STATUS_FINISHED:
            if orderInfo['MarketOrderFlag']:
                # 补单
                self.reissue_order( (order.totalVolume - order.tradedVolume) * (1 if order.direction == Direction.LONG else -1) ,self.tickAdd )

            del self.uncompletedOrders[orderkey]

            if len(self.uncompletedOrders) == 0:
                self.entrust = 0

            self.putEvent()  # 更新监控事件

    #----------------------------------------------------------------------
    def on_tick(self, tick):
        """收到行情推送"""
        super().on_tick(tick)
        # 更新策略执行的时间（用于回测时记录发生的时间）
        if self.uncompletedOrders:
            self.cancelLogic()

    # ----------------------------------------------------------------------
    def on_bar(self, bar):
        """分钟K线数据更新（仅用于回测时，从策略外部调用)"""
        super().on_bar(bar)
        # 更新策略执行的时间（用于回测时记录发生的时间）
        if self.uncompletedOrders:
            self.cancelLogic()

    # ----------------------------------------------------------------------
    def cancelLogic(self):
        "撤单逻辑" ""
        for order in list(self.uncompletedOrders.keys()):
            orderInfo = self.uncompletedOrders[order]
            if ((self.lastDatetime - orderInfo["OrderTime"]).seconds >=
                    self.cancelSeconds):  # 超过设置的时间还未成交
                # 取消
                orderInfo['MarketOrderFlag'] = True
                self.cancel_order(str(order))

    # ----------------------------------------------------------------------
    def buy_t(self, price, volume, stop=False):
        """买开"""
        orderID = super(CtaTemplate_1, self).buy(price, volume, stop)
        if orderID and not stop:
            self.entrust = 1  # 委托状态
            for ID in orderID:
                self.uncompletedOrders[ID] = {
                    'OrderTime': copy(self.lastDatetime),
                    'MarketOrderFlag':False
                }
        return orderID

    # ----------------------------------------------------------------------
    def sell_t(self, price, volume, stop=False):
        """卖平"""
        orderID = super(CtaTemplate_1, self).sell(price, volume, stop)
        if orderID and not stop:
            self.entrust = -1  # 置当前策略的委托单状态
            # 记录委托单
            for ID in orderID:
                self.uncompletedOrders[ID] = {
                    'OrderTime': copy(self.lastDatetime),
                    'MarketOrderFlag':False
                }
        return orderID

    # ----------------------------------------------------------------------
    def short_t(self, price, volume, stop=False):
        """卖开"""
        orderID = super(CtaTemplate_1, self).short(price, volume, stop)
        if orderID and not stop:
            self.entrust = -1  # 委托状态
            for ID in orderID:
                self.uncompletedOrders[ID] = {
                    'OrderTime': copy(self.lastDatetime),
                    'MarketOrderFlag':False
                }
        return orderID

    # ----------------------------------------------------------------------
    def cover_t(self, price, volume, stop=False):
        """买平"""
        orderID = super(CtaTemplate_1, self).cover(price, volume, stop)

        if orderID and not stop:
            self.entrust = 1  # 置当前策略的委托单状态
            # 记录委托单
            for ID in orderID:
                self.uncompletedOrders[ID] = {
                    'OrderTime': copy(self.lastDatetime),
                    'MarketOrderFlag':False
                }
        return orderID

    #----------------------------------------------------------------------
    def reissue_order(self,posChange,tickAdd, info = [0]):
        """补单交易"""
        if self.tickAdd == tickAdd:
            info[0] += 1
            print("reissue delay order: index ",info[0] ,self.lastDatetime)

        # 确定委托基准价格，有tick数据时优先使用，否则使用bar
        longPrice = 0
        shortPrice = 0
        
        if self.lastTick:
            if posChange > 0:
                longPrice = self.lastTick.askPrice1 + tickAdd
                if self.lastTick.upperLimit:
                    longPrice = min(longPrice, self.lastTick.upperLimit)         # 涨停价检查
            else:
                shortPrice = self.lastTick.bidPrice1 - tickAdd
                if self.lastTick.lowerLimit:
                    shortPrice = max(shortPrice, self.lastTick.lowerLimit)       # 跌停价检查
        else:
            if posChange > 0:
                longPrice = self.lastBar.close + tickAdd
            else:
                shortPrice = self.lastBar.close - tickAdd
        
        # 回测模式下，采用合并平仓和反向开仓委托的方式
        if self.get_engine_type() == EngineType.BACKTESTING:
            if posChange > 0:
                l = self.buy_t(longPrice, abs(posChange))
            else:
                l = self.short_t(shortPrice, abs(posChange))
        
        # 实盘模式下，首先确保之前的委托都已经结束（全成、撤销）
        # 然后先发平仓委托，等待成交后，再发送新的开仓委托
        else:
            # 买入
            if posChange > 0:
                # 若当前有空头持仓
                if self.pos < 0:
                    # 若买入量小于空头持仓，则直接平空买入量
                    if posChange < abs(self.pos):
                        l = self.cover_t(longPrice, posChange)
                    # 否则先平所有的空头仓位
                    else:
                        l = self.cover_t(longPrice, abs(self.pos))
                # 若没有空头持仓，则执行开仓操作
                else:
                    l = self.buy_t(longPrice, abs(posChange))
            # 卖出和以上相反
            else:
                if self.pos > 0:
                    if abs(posChange) < self.pos:
                        l = self.sell_t(shortPrice, abs(posChange))
                    else:
                        l = self.sell_t(shortPrice, abs(self.pos))
                else:
                    l = self.short_t(shortPrice, abs(posChange))

            