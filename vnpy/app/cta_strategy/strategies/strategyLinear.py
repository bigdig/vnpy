# encoding: UTF-8
"""
残差周期交叉策略:
"""

from __future__ import division
from vnpy.app.cta_strategy.ctaTemplatePatch import CtaTemplatePatch
import talib as ta

########################################################################
class LinearStrategy(CtaTemplatePatch):
    """残差周期交叉策略"""
    className = 'LinearStrategy'
    author = u'renxg'

    regPeriod = 60
    residualSmaPeriod = 12
    residualLmaPeriod = 36

    parameters = CtaTemplatePatch.parameters + [
        'regPeriod', 'residualSmaPeriod', 'residualLmaPeriod'
    ]

    #----------------------------------------------------------------------
    def onXminBar(self, bar):
        """收到X分钟K线"""
        super(LinearStrategy, self).onXminBar(bar)

        if not self.trading:
            return
        if not self.am.inited:
            return

        # 发出状态更新事件
        if self.trading:

            direction = self.getSignalPos()
            if self.pos == 0:
                #空仓，开新仓
                self.filterTrade(direction)
            else:
                #持仓相反，平仓 （没有方向时不平仓）
                if self.direction * direction < 0:
                    self.clearOrder()

    #----------------------------------------------------------------------
    def filterTrade(self, direction):
        """按规则过滤交易"""
        if direction == 0:
            return

        self.trade(self.fixedSize * direction)
        self.put_event()

    #----------------------------------------------------------------------
    def getSignalPos(self):
        """计算指标数据"""

        # 指标计算
        am = self.am
        prediction = ta.LINEARREG(am.close, self.regPeriod)
        residual = (am.close - prediction)
        residualSma = ta.MA(residual, self.residualSmaPeriod)
        residualLma = ta.MA(residual, self.residualLmaPeriod)

        residualUp = residualSma[-1] > residualLma[-1]
        residualDn = residualSma[-1] < residualLma[-1]

        # 进出场逻辑
        if (residualUp):
            return 1

        if (residualDn):
            return -1

        return 0
