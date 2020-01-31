# encoding: UTF-8
'''
本文件包含了CTA引擎中的策略开发用模板。
添加了一些基本的策略属性，变量。不做下单逻辑
'''
from vnpy.trader.constant import Direction
from .utility import tradeDictToJSON
from .ctaTemplate_3 import CtaTemplate_3
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
class CtaTemplate_4(CtaTemplate_3):
    """
    add pnl calculate
    """

    className = 'CtaTemplate_4'
    author = u'rxg'

    size = 10             # 合约大小，默认为1
    marketTradeValue = 0  #策略的交易市值
    
    parameters = CtaTemplate_3.parameters + ['size']
    varList = CtaTemplate_3.variables + \
                [
                'openPrice',
                'pnl',
                'marketTradeValue'
                ]

    #----------------------------------------------------------------------
    @property
    def pnl(self):
        """最新价格属性"""
        if abs(self.pos):
            return (
                self.lastPrice * self.pos - self.marketTradeValue) * self.size
        else:
            return 0
        pass

    #----------------------------------------------------------------------
    @pnl.setter
    def pnl(self, value):
        """最新价格属性"""
        pass

    #----------------------------------------------------------------------
    @property
    def openPrice(self):
        """开仓价"""
        if abs(self.pos):
            return self.marketTradeValue / self.pos
        else:
            return 0
        pass

    #----------------------------------------------------------------------
    @openPrice.setter
    def openPrice(self, value):
        """开仓价"""
        pass

    #-----------------------------------------------------------------
    def getWinPips(self):
        """取赢利点差"""
        if abs(self.pos):
            return self.pnl / abs(self.pos) / self.size
        else:
            return 0

    #----------------------------------------------------------------------
    def on_trade(self, trade: TradeData):
        """收到交易信息"""
        #Fix: 交易状态激活
        self.trading = True

        #实盘模式
        #if self.getEngineType() == ENGINETYPE_TRADING:
        # content = tradeDictToJSON(trade)
        # self.writeCtaLog(u'%s 交易: %s' % (self.tradeIndex, content))

        #清除对冲部分market value
        hedge = trade.volume - abs(self.pos)

        # 他位过零点充要条件（交易量一定比当前仓位大 且持仓方向已经形成）
        targetDirection = 1 if trade.direction == Direction.LONG else -1
        if hedge > 0 and targetDirection == self.direction:
            #清空
            self.marketTradeValue = 0
        else:
            hedge = 0

        #记录交易市值
        if trade.direction == Direction.LONG:
            self.marketTradeValue += trade.price * (trade.volume - hedge)
        else:
            self.marketTradeValue -= trade.price * (trade.volume - hedge)

        # 重新计算市值
        if self.pos == 0:
            self.marketTradeValue = 0
