# encoding: UTF-8
"""
TripleMaSignal
"""

from vnpy.app.cta_strategy import (
    TickData,
    BarData,
    BarGenerator,
    ArrayManager,
)
from vnpy.app.cta_strategy.ctaTemplatePatch import CtaSignalPatch                                         
import talib                                            

########################################################################
class TripleMaCrossSignal(CtaSignalPatch):
    """TripleMaSignal"""

    # 策略参数
    # 三均线长度设置
    maWindow1 = 2
    maWindow2 = 16
    maWindow3 = 39

    # ma最新值
    ma1 = 0
    ma2 = 0
    ma3 = 0

    #----------------------------------------------------------------------
    def __init__(self,strategy,KCircle=1):
        """Constructor"""
        super(TripleMaCrossSignal, self).__init__(strategy)

        self.bg = BarGenerator(self.onBar,KCircle,self.onXminBar)
        self.am = ArrayManager(size=100)

    #----------------------------------------------------------------------
    def onBar(self, bar):
        """K线更新"""
        self.bg.update_bar(bar)

    #----------------------------------------------------------------------
    def onXminBar(self, bar = BarData):
        """X Min Bar"""

        # 保存K线数据
        am = self.am
        am.update_bar(bar)
        if not am.inited:
            self.set_signal_pos(0)
            return

        if self.trading:
            self.updateSignal()

    #----------------------------------------------------------------------
    def updateSignal(self):
        """X Min Bar"""
        self.set_signal_pos( self.getSignal())
        pass

    #----------------------------------------------------------------------
    def getSignal(self):
        """生成信号"""

        ma1Array = self.am.sma(self.maWindow1, True)
        self.ma10 = ma1Array[-2]
        self.ma1 = ma1Array[-1]

        self.ma2 = self.am.sma(self.maWindow2, False)
        self.ma3 = self.am.sma(self.maWindow3, False)

        # 开多，上穿
        if self.ma1 > self.ma2 > self.ma3 and self.ma10 < self.ma2:
            return 1
        # 开空，下穿
        elif self.ma1 < self.ma2 < self.ma3 and self.ma10 > self.ma2:
            return -1

        return 0


# encoding: UTF-8
"""
TripleMaSignal
"""

########################################################################
class TripleMaSignal(CtaSignalPatch):
    """TripleMaSignal"""

    # 策略参数
    # 三均线长度设置
    maWindow1 = 10
    maWindow2 = 30
    maWindow3 = 90

    # ma最新值
    ma1 = 0
    ma2 = 0
    ma3 = 0

    #----------------------------------------------------------------------
    def __init__(self,strategy,KCircle=1):
        """Constructor"""
        super(TripleMaSignal, self).__init__(strategy)

        self.bg = BarGenerator(self.onBar,KCircle,self.onXminBar)
        self.am = ArrayManager(size=100)

    #----------------------------------------------------------------------
    def onBar(self, bar):
        """K线更新"""
        self.bg.update_bar(bar)

    #----------------------------------------------------------------------
    def onXminBar(self, bar = BarData):
        """X Min Bar"""

        # 保存K线数据
        am = self.am
        am.update_bar(bar)
        if not am.inited:
            self.set_signal_pos(0)
            return

        if self.trading:
            self.updateSignal()

    #----------------------------------------------------------------------
    def updateSignal(self):
        """X Min Bar"""
        self.set_signal_pos( self.getSignal())
        pass

    #----------------------------------------------------------------------
    def getSignal(self):
        """生成信号"""

        ma1Array = self.am.sma(self.maWindow1, True)
        self.ma10 = ma1Array[-2]
        self.ma1 = ma1Array[-1]

        self.ma2 = self.am.sma(self.maWindow2, False)
        self.ma3 = self.am.sma(self.maWindow3, False)

        # 开多，上穿
        if self.ma1 > self.ma2 > self.ma3 :
            return 1
        # 开空，下穿
        elif self.ma1 < self.ma2 < self.ma3:
            return -1

        return 0