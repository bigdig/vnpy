# encoding: UTF-8
'''
本文件包含了CTA引擎中的策略开发用模板。
添加了一些基本的策略属性，变量。不做下单逻辑
'''
from datetime import datetime
from .ctaTemplate_4 import CtaTemplate_4

########################################################################
class CtaTemplate_5(CtaTemplate_4):
    """
    add base utility
    """

    className = 'CtaTemplate_5'
    author = u'rxg'

    #----------------------------------------------------------------------
    def getVPINValue(self, VPINCircle=1,Special = False):
        """取VPIN-VPINMean"""
        #取VPIN Strategy
        vpin, cdf, preCDF = 0, 0, 0
        strategyName = 'Z_VPIN_' + self.vt_symbol
        if strategyName in self.ctaEngine.strategyDict:
            strategy = self.ctaEngine.strategyDict[strategyName]
            vpin, cdf, preCDF = strategy.getVPIN(VPINCircle,Special)
        else:
            self.writeCtaLog(u'strategy %s Not Found' % strategyName)

        #self.writeCtaLog(u'%s %s %s %s' %(VPINCircle,vpin,cdf,preCDF))
        return vpin, cdf, preCDF

    #----------------------------------------------------------------------
    def debugVPIN(self):
        """debug"""
        #取VPIN Strategy
        strategyName = 'Z_VPIN_' + self.vt_symbol
        if strategyName in self.ctaEngine.strategyDict:
            strategy = self.ctaEngine.strategyDict[strategyName]
            info = u'%s 交易: PNL = %s  HoldTime = %s' % (
                self.tradeIndex, self.pnl, self.holdTime)
            strategy.debug(info)
        else:
            self.writeCtaLog(u'strategy %s Not Found' % strategyName)

    #----------------------------------------------------------------------
    def getGARCHValue(self, GARCHCircle=60):
        """取 predicate standardMU sigma"""
        #取GARCH Strategy
        strategyName = 'Z_GARCH_' + self.vt_symbol + '_' + str(GARCHCircle)
        if strategyName in self.ctaEngine.strategyDict:
            strategy = self.ctaEngine.strategyDict[strategyName]
            return strategy.getGARCH(GARCHCircle, self.vt_symbol,
                                     self.lastDatetime)
        else:
            self.writeCtaLog(u'strategy %s Not Found' % strategyName)
            return (False, 0, 0, 0)

    #----------------------------------------------------------------------
    def getSigmaValue(self, GARCHCircle=60):
        """取 predicate standardMU sigma"""
        #取GARCH Strategy
        strategyName = 'Z_GARCH_' + self.vt_symbol + '_' + str(GARCHCircle)
        if strategyName in self.ctaEngine.strategyDict:
            strategy = self.ctaEngine.strategyDict[strategyName]
            result, predicate, mu, sigma = strategy.getGARCH(
                GARCHCircle, self.vt_symbol, self.lastDatetime)
            if result:
                return sigma
            else:
                return 0.008
        else:
            self.writeCtaLog(u'strategy %s Not Found' % strategyName)
            return 0.008

    #----------------------------------------------------------------------
    def getEMDTrend(self, Circle=3):
        """取EMDTrend"""
        #取VPIN Strategy
        trend = False
        strategyName = 'Z_EMDTrend_' + self.vt_symbol + '_' + str(Circle)
        if strategyName in self.ctaEngine.strategyDict:
            strategy = self.ctaEngine.strategyDict[strategyName]
            trend = strategy.getEMDTrend(Circle, self.vt_symbol,
                                         self.lastDatetime)
        else:
            self.writeCtaLog(u'strategy %s Not Found' % strategyName)

        return trend

    #----------------------------------------------------------------------
    def getCYQ(self):
        """取CYQ"""
        #取VPIN Strategy
        strategyName = 'Z_CYQ_' + self.vt_symbol
        if strategyName in self.ctaEngine.strategyDict:
            strategy = self.ctaEngine.strategyDict[strategyName]
            return strategy.getCYQ()
        else:
            self.writeCtaLog(u'strategy %s Not Found' % strategyName)

        return 0, 0, 0

