# encoding: UTF-8
'''
本文件包含了CTA引擎中的策略开发用模板。
添加了一些基本的策略属性，变量。不做下单逻辑
'''

from vnpy.trader.constant import Interval, Direction, Offset
from vnpy.app.cta_strategy.base import StopOrderStatus,StopOrder
from .ctaTemplate_1 import CtaTemplate_1
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
class CtaTemplate_2(CtaTemplate_1):
    """
    多空每个方向最多保存一个Stop Order
    """
    className = 'CtaTemplate_2'
    author = u'rxg'
    stopOrderDictory = None  #本策略的停止单

    #----------------------------------------------------------------------
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.stopOrderDictory = {}

    #----------------------------------------------------------------------
    def on_stop_order(self, stop_order: StopOrder):
        """停止单推送"""
        #如果已经设置移动止损单，撤消
        self.stopOrderDictory[stop_order.stop_orderid] = stop_order
        if stop_order.status in [StopOrderStatus.CANCELLED, StopOrderStatus.TRIGGERED]:
            self.stopOrderDictory.pop(stop_order.stop_orderid, None)
        pass

    #----------------------------------------------------------------------
    def send_order(
        self,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float,
        stop: bool = False,
        lock: bool = False
    ):
        """发送委托,只保留一个停止单"""
        if self.trading:
            # 如果stop为True，则意味着发本地停止单
            if stop:
                if self.stopOrderDictory:
                    # long stop order
                    if direction == Direction.LONG:
                        for order in self.stopOrderDictory.values():
                            if price >= order.price:
                                return []
                        # 去除旧的单子
                        for order in list(self.stopOrderDictory.values()):
                            self.cancel_order(order.stop_orderid)
                    else:
                        for order in self.stopOrderDictory.values():
                            if price <= order.price:
                                return []
                        # 去除旧的单子
                        for order in list(self.stopOrderDictory.values()):
                            self.cancel_order(order.stop_orderid)

        return super(CtaTemplate_2, self).send_order(direction, offset, price,
                                                       volume, stop, lock)
