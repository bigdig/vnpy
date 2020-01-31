from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Callable
from itertools import product
from functools import lru_cache
from time import time
import multiprocessing
import random

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pandas import DataFrame
from deap import creator, base, tools, algorithms

from vnpy.trader.constant import (Direction, Offset, Exchange,
                                  Interval, Status)
from vnpy.trader.database import database_manager
from vnpy.trader.object import OrderData, TradeData, BarData, TickData
from vnpy.trader.utility import round_to

from .base import (
    BacktestingMode,
    EngineType,
    STOPORDER_PREFIX,
    StopOrder,
    StopOrderStatus,
    INTERVAL_DELTA_MAP
)
from .template import CtaTemplate

from itertools import groupby
import traceback
import copy
import numpy as np

from .backtesting import *

sns.set_style("whitegrid")
creator.create("FitnessMax", base.Fitness, weights=(1.0,))
creator.create("Individual", list, fitness=creator.FitnessMax)


class BacktestingEnginePatch(BacktestingEngine):
    """"""

    def __init__(self):
        """"""
        super().__init__()

        # 清空 vtOrderID和strategy对象映射的字典（用于推送order和trade数据）
        self.orderStrategyDict = {}
        # key为策略名称，value为策略实例，注意策略名称不允许重复
        self.strategyDict = {}

    def clear_data(self):
        """
        Clear all data of last backtesting.
        """
        self.strategy = None
        self.tick = None
        self.bar = None
        self.datetime = None

        self.stop_order_count = 0
        self.stop_orders.clear()
        self.active_stop_orders.clear()

        self.limit_order_count = 0
        self.limit_orders.clear()
        self.active_limit_orders.clear()

        self.trade_count = 0
        self.trades.clear()

        self.logs.clear()
        self.daily_results.clear()

    #------------------------------------------------
    # 结果计算相关
    #------------------------------------------------
    #----------------------------------------------------------------------
    def calculateBacktestingResult(self):
        return self.calculateBacktestingResultImp(self.trades.values())

    #----------------------------------------------------------------------
    def calculateBacktestingResultImp(self, tradearray):
        """
        计算回测结果
        """
        # 首先基于回测后的成交记录，计算每笔交易的盈亏
        resultList = []  # 交易结果列表

        longTradeList = []  # 多头交易列表
        shortTradeList = []  # 空头交易列表

        longTrade = []  # 未平仓的多头交易
        shortTrade = []  # 未平仓的空头交易

        tradeTimeList = []  # 每笔成交时间戳
        posList = [0]  # 每笔成交后的持仓情况

        # 对每个策略实例进行独立核算
        for key, items in groupby(
                sorted(tradearray, key=lambda t: t.name), lambda t: t.name):

            tradeCount = len(resultList)
            for trade in items:
                # 复制成交对象，因为下面的开平仓交易配对涉及到对成交数量的修改
                # 若不进行复制直接操作，则计算完后所有成交的数量会变成0
                trade = copy.deepcopy(trade)

                #无交易量，不计算
                if trade.volume == 0:
                    pass
                # 多头交易
                elif trade.direction == Direction.LONG:
                    # 如果尚无空头交易
                    if not shortTrade:
                        longTrade.append(trade)
                    # 当前多头交易为平空
                    else:
                        while True:

                            # #多策略混合
                            # shortTradeIndex = 0
                            # entryTrade = None
                            # #找到策略名相对应的交易
                            # for index,val in enumerate(shortTrade):
                            #     if val.name == trade.name:
                            #         shortTradeIndex = index
                            #         entryTrade = val
                            #         break
                            #     else:
                            #         pass

                            entryTrade = shortTrade[0]
                            if not entryTrade:
                                longTrade.append(trade)
                                break
                            else:
                                exitTrade = trade

                                # 清算开平仓交易
                                closedVolume = min(exitTrade.volume,
                                                   entryTrade.volume)
                                result = TradingResult(
                                    entryTrade.price, entryTrade.datetime,
                                    exitTrade.price, exitTrade.datetime,
                                    -closedVolume, self.rate, self.slippage,
                                    self.size, key)
                                resultList.append(result)
                                shortTradeList.append(result.pnl)  # 加入多头交易

                                #posList.extend([-max(exitTrade.volume, entryTrade.volume),0])
                                #计算当前仓位
                                # pos = 0
                                # if longTrade:
                                #     for t in longTrade:
                                #         pos += t.volume
                                # if shortTrade:
                                #     for t in shortTrade:
                                #         pos -= t.volume
                                # posList.extend([pos,0])
                                # tradeTimeList.extend([result.entryDt, result.exitDt])

                                # 计算未清算部分
                                entryTrade.volume -= closedVolume
                                exitTrade.volume -= closedVolume

                                # 如果开仓交易已经全部清算，则从列表中移除
                                if not entryTrade.volume:
                                    shortTrade.pop(0)

                                # 如果平仓交易已经全部清算，则退出循环
                                if not exitTrade.volume:
                                    break

                                # 如果平仓交易未全部清算，
                                if exitTrade.volume:
                                    # 且开仓交易已经全部清算完，则平仓交易剩余的部分
                                    # 等于新的反向开仓交易，添加到队列中
                                    if not shortTrade:
                                        longTrade.append(exitTrade)
                                        break
                                    # 如果开仓交易还有剩余，则进入下一轮循环
                                    else:
                                        pass

                # 空头交易
                else:
                    # 如果尚无多头交易
                    if not longTrade:
                        shortTrade.append(trade)
                    # 当前空头交易为平多
                    else:
                        while True:

                            # #多策略混合
                            # longTradeIndex = 0
                            # entryTrade = None
                            # #找到策略名相对应的交易
                            # for index,val in enumerate(longTrade):
                            #     if val.name == trade.name:
                            #         longTradeIndex = index
                            #         entryTrade = val
                            #         break
                            #     else:
                            #         pass

                            entryTrade = longTrade[0]
                            if not entryTrade:
                                shortTrade.append(trade)
                                break
                            else:
                                exitTrade = trade

                                # 清算开平仓交易
                                closedVolume = min(exitTrade.volume,
                                                   entryTrade.volume)
                                result = TradingResult(
                                    entryTrade.price, entryTrade.datetime,
                                    exitTrade.price, exitTrade.datetime,
                                    closedVolume, self.rate, self.slippage,
                                    self.size, key)
                                resultList.append(result)
                                longTradeList.append(result.pnl)  # 加入空头交易
                                #计算当前仓位
                                # pos = 0
                                # if longTrade:
                                #     for t in longTrade:
                                #         pos += t.volume
                                # if shortTrade:
                                #     for t in shortTrade:
                                #         pos -= t.volume
                                # posList.extend([pos,0])
                                #posList.extend([max(exitTrade.volume, entryTrade.volume),0])
                                # tradeTimeList.extend([result.entryDt, result.exitDt])

                                # 计算未清算部分
                                entryTrade.volume -= closedVolume
                                exitTrade.volume -= closedVolume

                                # 如果开仓交易已经全部清算，则从列表中移除
                                if not entryTrade.volume:
                                    longTrade.pop(0)

                                # 如果平仓交易已经全部清算，则退出循环
                                if not exitTrade.volume:
                                    break

                                # 如果平仓交易未全部清算，
                                if exitTrade.volume:
                                    # 且开仓交易已经全部清算完，则平仓交易剩余的部分
                                    # 等于新的反向开仓交易，添加到队列中
                                    if not longTrade:
                                        shortTrade.append(exitTrade)
                                        break
                                    # 如果开仓交易还有剩余，则进入下一轮循环
                                    else:
                                        pass

            # 到最后交易日尚未平仓的交易，则以最后价格平仓
            if self.mode == BacktestingMode.BAR:
                endPrice = self.bar.close_price
            else:
                endPrice = self.tick.last_price

            for trade in longTrade:
                result = TradingResult(trade.price, trade.datetime, endPrice,
                                       self.datetime, trade.volume, self.rate,
                                       self.slippage, self.size, key)
                resultList.append(result)
                longTradeList.append(result.pnl)  # 加入空头交易

            for trade in shortTrade:
                result = TradingResult(trade.price, trade.datetime, endPrice,
                                       self.datetime, -trade.volume, self.rate,
                                       self.slippage, self.size, key)
                resultList.append(result)
                shortTradeList.append(result.pnl)  # 加入多头交易
                

            #clear
            longTrade = []  # 未平仓的多头交易
            shortTrade = []  # 未平仓的空头交易

            tc = len(resultList) - tradeCount
            if tc:
                self.output(u'%10s次交易\t%s' % (tc, key))

        # 检查是否有交易
        if not resultList:
            #self.output(u'无交易结果')
            noResult = {}
            noResult['capital'] = 0
            noResult['maxCapital'] = 0
            noResult['drawdown'] = 0
            noResult['totalResult'] = 0
            noResult['totalTurnover'] = 0
            noResult['totalCommission'] = 0
            noResult['totalSlippage'] = 0
            noResult['timeList'] = 0
            noResult['pnlList'] = 0
            noResult['capitalList'] = 0
            noResult['drawdownList'] = 0
            noResult['winningRate'] = 0
            noResult['averageWinning'] = 0
            noResult['averageLosing'] = 0
            noResult['profitLossRatio'] = 0
            noResult['posList'] = 0
            noResult['tradeTimeList'] = 0
            noResult['resultList'] = 0
            noResult['maxDrawdown'] = 0
            return noResult

        # 按时间排序
        resultList = sorted(resultList, key=lambda r: r.entryDt)
        resultList1 = sorted(resultList, key=lambda r: r.exitDt)
        tradeTimeList = []
        posList = []
        posIn = 0
        for result in resultList:
            tradeTimeList.extend([result.entryDt, result.exitDt])

            # 之前进场的+ volume, 之前出场的 - volume
            posIn += result.volume
            posOut = 0
            for r in resultList1:
                if r.exitDt < result.entryDt:
                    posOut += r.volume
                else:
                    break

            posList.extend([posIn - posOut, 0])

        # 然后基于每笔交易的结果，我们可以计算具体的盈亏曲线和最大回撤等
        capital = 0  # 资金
        maxCapital = 0  # 资金最高净值
        drawdown = 0  # 回撤
        drawdownpctList = []  # 回撤比例

        longPnl = 0  # 多仓平均利润
        if longTradeList:
            longPnl = np.array(longTradeList).mean()

        shortPnl = 0  # 空仓平均利润
        if shortTradeList:
            shortPnl = np.array(shortTradeList).mean()

        networthList = []  # 净值数据序列

        totalResult = 0  # 总成交数量
        totalTurnover = 0  # 总成交金额（合约面值）
        totalCommission = 0  # 总手续费
        totalSlippage = 0  # 总滑点

        timeList = []  # 时间序列
        pnlList = []  # 每笔盈亏序列
        pnlPctList = []  # 每笔百分比盈亏
        totalpnlPctList = []  # 每笔百分比盈亏序列
        capitalList = []  # 盈亏汇总的时间序列
        drawdownList = []  # 回撤的时间序列

        winningResult = 0  # 盈利次数
        losingResult = 0  # 亏损次数
        totalWinning = 0  # 总盈利金额
        totalLosing = 0  # 总亏损金额
        maxDrawdown = 0         # 最大回撤 

        for result in resultList:
            capital += result.pnl
            maxCapital = max(capital, maxCapital)
            drawdown = capital - maxCapital
            maxDrawdown = min(drawdown, maxDrawdown)

            #fix: 考虑本金的回撤
            ddpct = (drawdown + 1) / (
                maxCapital + self.capital) if maxCapital != 0 else (
                    0 + 0.01)  # 最大回撤百分比
            drawdownpctList.append(ddpct)  # 最大回撤

            networth = 1 + (capital / self.capital)
            networthList.append(networth)

            pnlList.append(result.pnl)
            pnlPctList.append(result.pnlPct)
            timeList.append(result.exitDt)  # 交易的时间戳使用平仓时间
            capitalList.append(capital)
            drawdownList.append(drawdown)

            totalResult += 1
            totalTurnover += result.turnover
            totalCommission += result.commission
            totalSlippage += result.slippage

            if result.pnl >= 0:
                winningResult += 1
                totalWinning += result.pnl
            else:
                losingResult += 1
                totalLosing += result.pnl

        # 计算盈亏相关数据
        winningRate = winningResult / totalResult * 100  # 胜率

        averageWinning = 0  # 这里把数据都初始化为0
        averageLosing = 0
        profitLossRatio = 0

        if winningResult:
            averageWinning = totalWinning / winningResult  # 平均每笔盈利
        if losingResult:
            averageLosing = totalLosing / losingResult  # 平均每笔亏损
        if averageLosing:
            profitLossRatio = -averageWinning / averageLosing  # 盈亏比

        # 返回回测结果
        d = {}
        d['capital'] = capital
        d['maxCapital'] = maxCapital
        d['drawdown'] = drawdown
        d['totalResult'] = totalResult
        d['totalTurnover'] = totalTurnover
        d['totalCommission'] = totalCommission
        d['totalSlippage'] = totalSlippage
        d['timeList'] = timeList
        d['pnlList'] = pnlList
        d['pnlPctList'] = pnlPctList
        d['capitalList'] = capitalList
        d['drawdownList'] = drawdownList
        d['winningRate'] = winningRate
        d['averageWinning'] = averageWinning
        d['averageLosing'] = averageLosing
        d['profitLossRatio'] = profitLossRatio
        d['posList'] = posList
        d['tradeTimeList'] = tradeTimeList
        d['drawdownpctList'] = drawdownpctList  #
        d['networthList'] = networthList
        d['longPnl'] = longPnl
        d['shortPnl'] = shortPnl
        d['longTradeCount'] = len(longTradeList)
        d['shortTradeCount'] = len(shortTradeList)
        d['resultList'] = resultList
        d['maxDrawdown']  = maxDrawdown

        try:
            # 显示定单信息
            import pandas as pd
            orders = pd.DataFrame([i.__dict__ for i in resultList])
            try:
                orders['holdTime'] = (
                    orders.exitDt - orders.entryDt).astype('timedelta64[m]')
            except:
                pass
            pd.options.display.max_rows = 100
            pd.options.display.width = 300
            pd.options.display.precision = 2
            self.output('-' * 50)
            self.output(str(orders))
        except:
            print('-' * 20)
            print('Failed to print result')
            #traceback.print_exc()

        return d

    #----------------------------------------------------------------------
    def showBacktestingResult(self):
        # 对每个策略实例进行独立核算
        for key, items in groupby(
                sorted(self.trades.values(), key=lambda t: t.name),
                lambda t: t.name):
            self.showBacktestingResultImp(list(items))

        return self.showBacktestingResultImp(list(self.trades.values()))

    #----------------------------------------------------------------------
    def showBacktestingResultImp(self, tradearray):
        """显示回测结果"""
        d = self.calculateBacktestingResultImp(tradearray)
        if not d or not d['timeList']:
            return

        trueTimeDelta = (365. / ((self.end - self.start).days + 1)) if self.end else \
                        (365. / ((d['timeList'][-1] - self.start).days + 1))
        minbin = 5.
        try:
            annualizedRet = (d['networthList'][-1])**trueTimeDelta - 1.
        #  ret = (mean((array(d['networthList'])[1:] - array(d['networthList'])[:-1]) / array(d['networthList'])[:-1]))
        # annualizedStd = std((array(d['networthList'])[1:] - array(d['networthList'])[:-1]) / array(d['networthList'])[:-1]) \
        #                * sqrt(225.* 250./ minbin)
        #self.output(u'时间：\t%s' % formatNumber( trueTimeDelta ))
        #self.output(u'年化波动率分子：\t%s' % formatNumber\
        #   (std((array(d['networthList'])[1:] - array(d['networthList'])[:-1]) / array(d['networthList'])[:-1])))
        #self.output(u'年化波动率总分母：\t%s' % formatNumber(sqrt(225.* 250./ minbin)))
        #sharpeRatio = ((ret + 1) ** (225.* 250./ minbin) - 1) / annualizedStd
        except:
            self.output(u'净值为负')

        # 输出
        self.output('-' * 50)
        # self.output(u'第一笔交易：\t%s' % d['timeList'][0])
        # self.output(u'最后一笔交易：\t%s' % d['timeList'][-1])

        # self.output(u'总交易次数：\t%s' % formatNumber(d['totalResult']))
        # self.output(u'多头交易次数：\t%s' % formatNumber(d['longTradeCount']))
        # self.output(u'空头交易次数：\t%s' % formatNumber(d['shortTradeCount']))
        # self.output(u'期末净值：\t%s' % formatNumber(d['networthList'][-1]))
        # self.output(u'总盈亏：\t%s' % formatNumber(d['capital']))
        # self.output(u'最大回撤: \t%s' % formatNumber(min(d['drawdownList'])))
        # self.output(u'最大回撤百分比: \t%s' % formatNumber(min(d['drawdownpctList'])))

        # try:
        #     self.output(u'年化收益率：\t%s' % formatNumber(annualizedRet))
        #     #self.output(u'夏普比率：\t%s' % formatNumber(sharpeRatio))
        #     self.output(u'收益回撤比: \t%s' % formatNumber(
        #         ((d['networthList'][-1]) ** trueTimeDelta - 1.) / min(d['drawdownpctList'])))
        # except:
        #     self.output(u'净值为负！')

        # self.output(u'平均每笔盈利：\t%s' %formatNumber(d['capital']/d['totalResult']))
        # self.output(u'平均每笔滑点：\t%s' %formatNumber(d['totalSlippage']/d['totalResult']))
        # self.output(u'平均每笔佣金：\t%s' %formatNumber(d['totalCommission']/d['totalResult']))

        # self.output(u'胜率\t\t%s%%' %formatNumber(d['winningRate']))
        # self.output(u'盈利交易平均值\t%s' %formatNumber(d['averageWinning']))
        # self.output(u'亏损交易平均值\t%s' %formatNumber(d['averageLosing']))
        # self.output(u'盈亏比：\t%s' %formatNumber(d['profitLossRatio']))
        # self.output(u'多仓平均利润：\t%s' % formatNumber(d['longPnl']))
        # self.output(u'空仓平均利润：\t%s' % formatNumber(d['shortPnl']))

        try:
            # 显示结果信息
            import pandas as pd
            info = [
                [u'第一笔交易', d['timeList'][0]],
                [u'最后一笔交易', d['timeList'][-1]],
                [u'总交易次数', formatNumber(d['totalResult'])],
                [u'多头交易次数', formatNumber(d['longTradeCount'])],
                [u'空头交易次数', formatNumber(d['shortTradeCount'])],
                [u'期末净值', formatNumber(d['networthList'][-1])],
                [u'总盈亏', formatNumber(d['capital'])],
                [u'年化收益率', formatNumber(annualizedRet)],
                [
                    u'收益回撤比',
                    formatNumber(((d['networthList'][-1])**trueTimeDelta - 1.)
                                 / min(d['drawdownpctList']))
                ],
                [u'最大回撤', formatNumber(d['maxDrawdown'])],
                [u'最大回撤百分比',
                 formatNumber(min(d['drawdownpctList']))],
                [u'平均每笔盈利',
                 formatNumber(d['capital'] / d['totalResult'])],
                [
                    u'平均每笔滑点',
                    formatNumber(d['totalSlippage'] / d['totalResult'])
                ],
                [
                    u'平均每笔佣金',
                    formatNumber(d['totalCommission'] / d['totalResult'])
                ],
                [u'胜率', formatNumber(d['winningRate'])],
                [u'盈利交易平均值', formatNumber(d['averageWinning'])],
                [u'亏损交易平均值', formatNumber(d['averageLosing'])],
                [u'盈亏比', formatNumber(d['profitLossRatio'])],
                [u'多仓平均利润', formatNumber(d['longPnl'])],
                [u'空仓平均利润', formatNumber(d['shortPnl'])],
            ]

            info = pd.DataFrame(info)
            pd.options.display.max_rows = 999
            pd.options.display.width = 500
            pd.options.display.precision = 2
            pd.options.display.unicode.east_asian_width = True
            self.output(str(info))
        except:
            print('-' * 20)
            print('Failed to print result')
            traceback.print_exc()

        # 绘图
        #fig = plt.figure(figsize=(10, 16))

        try:
            import matplotlib.pyplot as plt
            pCapital = plt.subplot(4, 1, 1)
            pCapital.set_ylabel("capital")
            pCapital.plot(d['capitalList'], color='r', lw=0.8)

            pDD = plt.subplot(4, 1, 2)
            pDD.set_ylabel("DD")
            pDD.bar(
                range(len(d['drawdownList'])), d['drawdownList'], color='g')

            pPnl = plt.subplot(4, 1, 3)
            pPnl.set_ylabel("pnl")
            if len(d['pnlList']) > 1:
                if len(d['pnlList']) > 100:
                    pPnl.hist(d['pnlList'], bins=50, color='c',log = True)
                else:
                    pPnl.hist(d['pnlList'], bins=50, color='c',log = False)

            pPos = plt.subplot(4, 1, 4)
            pPos.set_ylabel("Position")
            if d['posList'][-1] == 0:
                del d['posList'][-1]
            tradeTimeIndex = [
                #item.strftime("%m/%d %H:%M:%S") for item in d['tradeTimeList']
                item.strftime("%Y-%m-%d") for item in d['tradeTimeList']
                
            ]
            xindex = np.arange(0, len(tradeTimeIndex),
                               max(1, np.int(len(tradeTimeIndex) / 5)))
            tradeTimeIndex = list(map(lambda i: tradeTimeIndex[i], xindex))
            pPos.plot(d['posList'], color='k', drawstyle='steps-pre')
            plt.sca(pPos)
            plt.tight_layout()
            plt.xticks(xindex, tradeTimeIndex, rotation=0)  # 旋转15

            # plt.show()

            names = []
            for key, items in groupby(
                    sorted(tradearray, key=lambda t: t.name),
                    lambda t: t.name):
                names.append(key)

            plt.savefig('./temp/' + '_'.join(names)[:50] + '.png', dpi=200)
            plt.close()

        except ImportError as identifier:
            print('-' * 20)
            print('Failed to ImportError pyplot')
            ##traceback.print_exc()
        except:
            print('-' * 20)
            print('Failed to plot capital curve')
            traceback.print_exc()

        return d


    def cross_limit_order(self):
        """
        Cross limit order with last bar/tick data.
        """
        if self.mode == BacktestingMode.BAR:
            long_cross_price = self.bar.low_price
            short_cross_price = self.bar.high_price
            long_best_price = self.bar.open_price
            short_best_price = self.bar.open_price
        else:
            long_cross_price = self.tick.ask_price_1
            short_cross_price = self.tick.bid_price_1
            long_best_price = long_cross_price
            short_best_price = short_cross_price

        for order in list(self.active_limit_orders.values()):
            # Push order update with status "not traded" (pending).
            if order.status == Status.SUBMITTING:
                order.status = Status.NOTTRADED
                #self.strategy.on_order(order)
                strategy = self.orderStrategyDict[order.vt_orderid]
                strategy.on_order(order)

            # Check whether limit orders can be filled.
            long_cross = (
                order.direction == Direction.LONG
                and order.price >= long_cross_price
                and long_cross_price > 0
            )

            short_cross = (
                order.direction == Direction.SHORT
                and order.price <= short_cross_price
                and short_cross_price > 0
            )

            if not long_cross and not short_cross:
                continue

            #增加多策略测试
            # 将成交推送到策略对象中
            if order.vt_orderid in self.orderStrategyDict:
                strategy = self.orderStrategyDict[order.vt_orderid]

            # Push order udpate with status "all traded" (filled).
            order.traded = order.volume
            order.status = Status.ALLTRADED
            strategy.on_order(order)

            self.active_limit_orders.pop(order.vt_orderid)

            # Push trade update
            self.trade_count += 1

            if long_cross:
                trade_price = min(order.price, long_best_price)
                pos_change = order.volume
            else:
                trade_price = max(order.price, short_best_price)
                pos_change = -order.volume

            trade = TradeData(
                symbol=order.symbol,
                exchange=order.exchange,
                orderid=order.orderid,
                tradeid=str(self.trade_count),
                direction=order.direction,
                offset=order.offset,
                price=trade_price,
                volume=order.volume,
                time=self.datetime.strftime("%H:%M:%S"),
                gateway_name=self.gateway_name,
            )
            trade.datetime = self.datetime
            #add trade strategy name, 以便于区别多策略混合效果
            trade.name = strategy.strategy_name

            strategy.pos += pos_change
            strategy.on_trade(trade)

            self.trades[trade.vt_tradeid] = trade

    def cross_stop_order(self):
        """
        Cross stop order with last bar/tick data.
        """
        if self.mode == BacktestingMode.BAR:
            long_cross_price = self.bar.high_price
            short_cross_price = self.bar.low_price
            long_best_price = self.bar.open_price
            short_best_price = self.bar.open_price
        else:
            long_cross_price = self.tick.last_price
            short_cross_price = self.tick.last_price
            long_best_price = long_cross_price
            short_best_price = short_cross_price

        for stop_order in list(self.active_stop_orders.values()):
            # Check whether stop order can be triggered.
            long_cross = (
                stop_order.direction == Direction.LONG
                and stop_order.price <= long_cross_price
            )

            short_cross = (
                stop_order.direction == Direction.SHORT
                and stop_order.price >= short_cross_price
            )

            if not long_cross and not short_cross:
                continue

            # Create order data.
            self.limit_order_count += 1

            order = OrderData(
                symbol=self.symbol,
                exchange=self.exchange,
                orderid=str(self.limit_order_count),
                direction=stop_order.direction,
                offset=stop_order.offset,
                price=stop_order.price,
                volume=stop_order.volume,
                status=Status.ALLTRADED,
                gateway_name=self.gateway_name,
            )
            order.datetime = self.datetime

            self.limit_orders[order.vt_orderid] = order

            # Create trade data.
            if long_cross:
                trade_price = max(stop_order.price, long_best_price)
                pos_change = order.volume
            else:
                trade_price = min(stop_order.price, short_best_price)
                pos_change = -order.volume

            self.trade_count += 1

            trade = TradeData(
                symbol=order.symbol,
                exchange=order.exchange,
                orderid=order.orderid,
                tradeid=str(self.trade_count),
                direction=order.direction,
                offset=order.offset,
                price=trade_price,
                volume=order.volume,
                time=self.datetime.strftime("%H:%M:%S"),
                gateway_name=self.gateway_name,
            )
            trade.datetime = self.datetime

            strategy = self.orderStrategyDict[stop_order.stop_orderid]
            #add trade strategy name, 以便于区别多策略混合效果
            trade.name = strategy.strategy_name

            self.trades[trade.vt_tradeid] = trade

            # Update stop order.
            stop_order.vt_orderids.append(order.vt_orderid)
            stop_order.status = StopOrderStatus.TRIGGERED

            if stop_order.stop_orderid in self.active_stop_orders:
                self.active_stop_orders.pop(stop_order.stop_orderid)

            # Push update to strategy.
            strategy.on_stop_order(stop_order)
            strategy.on_order(order)

            strategy.pos += pos_change
            strategy.on_trade(trade)

    def send_order(
        self,
        strategy: CtaTemplate,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float,
        stop: bool,
        lock: bool
    ):
        """"""
        price = round_to(price, self.pricetick)
        if stop:
            vt_orderid = self.send_stop_order(direction, offset, price, volume)
        else:
            vt_orderid = self.send_limit_order(direction, offset, price, volume)

        self.orderStrategyDict[vt_orderid] = strategy  # 保存vtOrderID和策略的映射关系
        return [vt_orderid]

########################################################################
class TradingResult(object):
    """每笔交易的结果"""

    #----------------------------------------------------------------------
    def __init__(self, entryPrice, entryDt, exitPrice, exitDt, volume, rate,
                 slippage, size, name):
        """Constructor"""
        self.entryPrice = entryPrice  # 开仓价格
        self.exitPrice = exitPrice  # 平仓价格

        self.entryDt = entryDt  # 开仓时间datetime
        self.exitDt = exitDt  # 平仓时间

        self.volume = volume  # 交易数量（+/-代表方向）

        self.turnover = (self.entryPrice + self.exitPrice) * size * abs(
            volume)  # 成交金额
        self.commission = self.turnover * rate  # 手续费成本
        self.slippage = slippage * 2 * size * abs(volume)  # 滑点成本
        self.pnl = ((self.exitPrice - self.entryPrice) * volume * size -
                    self.commission - self.slippage)  # 净盈亏
        self.pnlPct = self.pnl / self.entryPrice  # 百分比净盈亏

        self.name = name

