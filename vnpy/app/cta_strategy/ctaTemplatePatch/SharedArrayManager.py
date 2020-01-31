# encoding: UTF-8

'''
SharedArrayManager
'''
from __future__ import division
import talib
import datetime
import numpy as np
import pandas as pd
from collections import OrderedDict,defaultdict
from vnpy.app.cta_strategy import ArrayManager
# from zigzag import peak_valley_pivots, max_drawdown, compute_segment_returns, pivots_to_modes
# from vnpy.trader.app.ctaStrategy.VPINAnalysis import VPINAnalysisImp
from copy import copy

def getSharedArrayManager(vt_symbol,kLineCycle,KLineSeconds,size):
    return SharedArrayManager(size)

########################################################################
class SharedArrayManager(ArrayManager):
    """
    shared array manager
    """
    #----------------------------------------------------------------------
    def hhv(self, n, array=False):
        """移动最高"""
        result = talib.MAX(self.high, n)
        if array:
            return result
        return result[-1]

    #----------------------------------------------------------------------
    def llv(self, n, array=False):
        """移动最低"""
        result = talib.MAX(self.high, n)
        if array:
            return result
        return result[-1]

    #----------------------------------------------------------------------
    def kdj(self, n, s, f, array=False):
        """KDJ指标"""
        c   = self.close
        hhv = self.hhv(n)
        llv = self.llv(n)
        shl = talib.SUM(hhv-llv,s)
        scl = talib.SUM(c-llv,s)
        k   = 100*shl/scl
        d   = talib.SMA(k,f)
        j   = 3*k - 2*d
        if array:
            return k,d,j
        return k[-1],d[-1],j[-1]

    #----------------------------------------------------------------------
    
    def sma(self, n, array=False):
        """简单均线"""
        result = talib.SMA(self.close, n)
        if array:
            return result
        return result[-1]

    #----------------------------------------------------------------------
    
    def std(self, n, array=False):
        """标准差"""
        result = talib.STDDEV(self.close, n)
        if array:
            return result
        return result[-1]

    #----------------------------------------------------------------------
    def cci(self, n, array=False):
        """CCI指标"""
        result = talib.CCI(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]

    #----------------------------------------------------------------------
    def kd(self, nf=9, ns=3, array=False):
        """KD指标"""
        slowk, slowd = talib.STOCH(self.high, self.low, self.close,
                        fastk_period=nf,
                        slowk_period=ns,
                        slowk_matype=0,
                        slowd_period=ns,
                        slowd_matype=0)
        if array:
            return slowk, slowd
        return slowk[-1], slowd[-1]

    #----------------------------------------------------------------------
    def vol(self, n, array=False):
        """波动率指标"""
        logrtn = talib.LN(self.high/self.low)
        stdrtn = talib.STDDEV(logrtn,n)
        vol    = talib.EXP(stdrtn)-1
        if array:
            return vol
        return vol[-1]

    #----------------------------------------------------------------------
    
    def atr(self, n, array=False):
        """ATR指标"""
        result = talib.ATR(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]

    #----------------------------------------------------------------------
    def cmi(self, n, array=False):
        """CMI指标"""
        hhm = max(self.high[-n:])
        llm = min(self.low[-n:])
        delta = abs(self.close[-1]-self.close[-n])
        result = delta/(hhm-llm)
        return result

    #----------------------------------------------------------------------
    def rsi(self, n, array=False):
        """RSI指标"""
        result = talib.RSI(self.close, n)
        if array:
            return result
        return result[-1]

    #----------------------------------------------------------------------
    def macd(self, fastPeriod, slowPeriod, signalPeriod, array=False):
        """MACD指标"""
        macd, signal, hist = talib.MACD(self.close, fastPeriod,
                                        slowPeriod, signalPeriod)
        if array:
            return macd, signal, hist
        return macd[-1], signal[-1], hist[-1]

    #----------------------------------------------------------------------
    def adx(self, n, array=False):
        """ADX指标"""
        result = talib.ADX(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]

    #----------------------------------------------------------------------
    def peak(self, lookahead=100, delta=5, array=False):
        """峰值"""
        from .peakdetect import peakdetect
        size = min(self.count,self.size-1)
        maxP,minP = peakdetect(self.closeArray[-size:],lookahead=lookahead,delta=delta)
        if array:
            return maxP,minP
        return maxP,minP

    #----------------------------------------------------------------------
    def boll(self, n, dev, array=False):
        """布林通道"""
        mid = self.sma(n, array)
        std = self.std(n, array)

        up = mid + std * dev
        down = mid - std * dev

        return up, down

    #----------------------------------------------------------------------
    def keltner(self, n, dev, array=False):
        """肯特纳通道"""
        mid = self.sma(n, array)
        atr = self.atr(n, array)

        up = mid + atr * dev
        down = mid - atr * dev

        return up, down

    #----------------------------------------------------------------------
    def donchian(self, n, array=False):
        """唐奇安通道"""
        up = talib.MAX(self.high, n)
        down = talib.MIN(self.low, n)

        if array:
            return up, down
        return up[-1], down[-1]

    def aroon(self, n, array=False):
        """
        Aroon indicator.
        """
        aroon_up, aroon_down = talib.AROON(self.high, self.low, n)

        if array:
            return aroon_up, aroon_down
        return aroon_up[-1], aroon_down[-1]

    #----------------------------------------------------------------------
    def channelIndicator(self):
        """通道指数 atr/std，1 通道水平波动 <0.5 趋势明显 （0.5-0.6) 突破临界区"""
        window = self.size//2
        indicator = self.atr(window) / self.std(window)
        return indicator

    #---------------------------------------------------------------------
    
    def liquidity(self, n=0):
        """n：之前N根K线"""
        high = max(self.high[-n-1:])
        low = min(self.low[-n-1:])
        open = self.open[-n-1]
        close = self.close[-1]

        vt = sum(self.diffVolume[-n-1:])

        deltaNt = self.openInterest[-1] - self.openInterest[-2 - n]  #当前持仓量的变化

        #bug-fix + 1,avoid zero divid
        dt = vt - deltaNt + 1  #单位时间内对冲交易量
        mt = dt + vt + 1  #开出的总仓单量
        lt = dt / mt
        sigma = (self.atr(self.size // 2) + 0.01) / close
        liquidity = abs(np.log(open) - np.log(close)) / lt / sigma
        return liquidity

    """
    获得赫斯特指数。
    赫斯特指数将时间序列数据的方差看作扩散率，
    它是检查它是随机游走还是正常进程。
    f（x）=τ（**）（2H）
    如果Hurst指数的值为H <0.5，则表示存在平均回归，当H> 0.5时，存在趋势趋势
    有
    """
    def calcHurstExponent(self,lags_count=100):
        df = self.close
        lags = range(2, lags_count)
        ts = np.log(df)

        tau = [np.sqrt(np.std(np.subtract(ts[lag:], ts[:-lag]))) for lag in lags]
        poly = np.polyfit(np.log(lags), np.log(tau), 1)

        result = poly[0]*2.0

        return result

    """
    半衰期
    半衰期，t（1/2）=  - （ln2 / lambda）
    如果难以确定是否应用Hurst指数和ADF检验的平均回归模型
    确定半衰期。
    半衰期意味着价值恢复到平均水平所需的时间，
    我们可以找到可应用于平均回归模型的股票价格。
    - > Lambda是平均回归率，（myu）是平均值，dWt是误差项
         dX（t）=λ（（myu）-X（t））dt + sigma * dW（t）
         λ=（dX（t）-σ* dW（t））/（（myu）-X（t））dt） 
    """

    
    def calcHalfLife(self):
        df = self.close
        half_life = 0
        success = True
        try:
            price = pd.Series(df)
            lagged_price = price.shift(1).fillna(method="bfill")
            delta = price - lagged_price
            _lambda = np.polyfit(lagged_price, delta, 1)[0]
            if _lambda != 0:
                half_life = (-1*np.log(2)/_lambda)
            else:
                success = False
        except RuntimeWarning:
            success = False

        return success, half_life

    #----------------------------------------------------------------------
    def sar(self, array=False):
        result = talib.SAR(self.highArray, self.lowArray)
        if array:
            return result
        return result[-1]

    #----------------------------------------------------------------------
    def obv(self, array=False):
        result = talib.OBV(self.closeArray, self.diffVolume)
        if array:
            return result
        return result[-1]

    #----------------------------------------------------------------------
    
    def atrIsUp(self, n = 10, array=False):
        """ATR指标上升"""
        # ATR数值上穿其移动平均线，说明行情短期内波动加大
        # 即处于趋势的概率较大，适合CTA开仓
        atrArray = self.atr(n,array=True)
        atrMa = talib.MA(atrArray,n*2)[-1]
        atrValue = atrArray[-1]
        return atrValue > atrMa

    #----------------------------------------------------------------------
    
    def get_zigPrice(self,threshold = 0.005):
        ##zigzag for price
        try:
            pivots = peak_valley_pivots(self.close, threshold, -threshold)
            zigPrice = compute_segment_returns(self.close, pivots)
            if zigPrice.any():
                return zigPrice[-1]
            else:
                return 0
        except:
            return 0

    def get_zigVolume(self,threshold = 0.1):
        ##zigzag for Volume
        try:
            volumeDs = self.diffVolume
            pivotV = peak_valley_pivots(volumeDs, threshold, -threshold)
            zigVolume = compute_segment_returns( volumeDs, pivotV)
            if zigVolume.any():
                return zigVolume[-1]
            else:
                return 0
        except:
            return 0

    def get_zigOpenInterest(self,threshold = 0.5):
        ##zigzag for Interest
        try:
            volumeDs = np.diff(self.openInterest)
            pivotV = peak_valley_pivots(volumeDs, threshold, -threshold)
            zigVolume = compute_segment_returns( volumeDs, pivotV)
            if zigVolume.any():
                return zigVolume[-1]
            else:
                return 0
        except:
            return 0

    #----------------------------------------------------------------------
    
    def getATRSlope(self,volatilityWindow = 15):
        """取ATR斜率"""
        volatilityArray = talib.ATR(self.high, self.low, self.close,
                                 volatilityWindow)
        volatilityThreshold = talib.LINEARREG_SLOPE(
            volatilityArray, volatilityWindow)
        if volatilityThreshold[-1] > 0:
            return 1
        elif volatilityThreshold[-1] <= 0:
            return -1
        return 0

    #----------------------------------------------------------------------
    def vpin(self,minutes = 1,saveVPINPicture = False, fileInfo = "", specail = False):
        """返回VPIN - meanVPIN,CDF"""
        time = np.arange(self.size)
        price = self.closeArray

        # special计算的VPIN > 0 < 0 更理想点
        if specail:
            volume = self.diffVolumeSpecial
        else:
            volume = self.diffVolume

        meanValume = np.sum(volume)/(self.size*1.2)
        vpin,vpin_fintime = VPINAnalysisImp(time,price,volume,debug = saveVPINPicture,V = meanValume*minutes,numbuckets = 50)

        volumeBuckets = pd.DataFrame({'VPIN': vpin})
        volumeBuckets['CDF'] = volumeBuckets['VPIN'].rank(pct=True)
        window = min(100,volumeBuckets['CDF'].count()//2)
        volumeBuckets['VPINMean'] = volumeBuckets['VPIN'].rolling(window).mean()

        #输出图片
        if saveVPINPicture:
            #归一化
            p = np.array([price[x] for x in vpin_fintime])
            p = (p-p.min())/(p.max() - p.min())
            volumeBuckets['Price'] = p
            ax = volumeBuckets.plot()
            ax.figure.savefig("VPIN_CDF_"+ str(minutes) + "minutes_" + fileInfo + ".png",dpi=200)

        vpinRelative = vpin[-1] - volumeBuckets['VPINMean'].values[-1]
        vpinCDF = volumeBuckets['CDF'].values[-1]
        vpinCDFPre = volumeBuckets['CDF'].values[-2]
        return vpinRelative,vpinCDF,vpinCDFPre

    #--------------------------------------------------------------------------
    def getTrend(self,fastWindow = 6, slowWindow = 30):
        trendFastArray = talib.LINEARREG_SLOPE(self.close, fastWindow)
        trendSlowArray = talib.LINEARREG_SLOPE(self.close, slowWindow)

        if trendFastArray[-1] > trendSlowArray[-1] or trendFastArray[-1] > 0:
            Trend = 1

        elif trendFastArray[-1] < trendSlowArray[-1] or trendSlowArray[-1] < 0:
            Trend = -1
        else:
            Trend = 0

        return Trend