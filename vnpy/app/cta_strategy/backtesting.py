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

sns.set_style("whitegrid")
creator.create("FitnessMax", base.Fitness, weights=(1.0,))
creator.create("Individual", list, fitness=creator.FitnessMax)


class OptimizationSetting:
    """
    Setting for runnning optimization.
    """

    def __init__(self):
        """"""
        self.params = {}
        self.target_name = ""

    def add_parameter(
        self, name: str, start: float, end: float = None, step: float = None
    ):
        """"""
        if not end and not step:
            self.params[name] = [start]
            return

        if start >= end:
            print("参数优化起始点必须小于终止点")
            return

        if step <= 0:
            print("参数优化步进必须大于0")
            return

        value = start
        value_list = []

        while value <= end:
            value_list.append(value)
            value += step

        self.params[name] = value_list

    def set_target(self, target_name: str):
        """"""
        self.target_name = target_name

    def generate_setting(self):
        """"""
        keys = self.params.keys()
        values = self.params.values()
        products = list(product(*values))

        settings = []
        for p in products:
            setting = dict(zip(keys, p))
            settings.append(setting)

        return settings

    def generate_setting_ga(self):
        """"""
        settings_ga = []
        settings = self.generate_setting()
        for d in settings:
            param = [tuple(i) for i in d.items()]
            settings_ga.append(param)
        return settings_ga


class BacktestingEngine:
    """"""

    engine_type = EngineType.BACKTESTING
    gateway_name = "BACKTESTING"

    def __init__(self):
        """"""
        self.vt_symbol = ""
        self.symbol = ""
        self.exchange = None
        self.start = None
        self.end = None
        self.rate = 0
        self.slippage = 0
        self.size = 1
        self.pricetick = 0
        self.capital = 1_000_000
        self.mode = BacktestingMode.BAR
        self.inverse = False

        self.strategy_class = None
        self.strategy = None
        self.tick: TickData
        self.bar: BarData
        self.datetime = None

        self.interval = None
        self.days = 0
        self.callback = None
        self.history_data = []

        self.stop_order_count = 0
        self.stop_orders = {}
        self.active_stop_orders = {}

        self.limit_order_count = 0
        self.limit_orders = {}
        self.active_limit_orders = {}

        self.trade_count = 0
        self.trades = {}

        self.logs = []

        self.daily_results = {}
        self.daily_df = None

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

    def set_parameters(
        self,
        vt_symbol: str,
        interval: Interval,
        start: datetime,
        rate: float,
        slippage: float,
        size: float,
        pricetick: float,
        capital: int = 0,
        end: datetime = None,
        mode: BacktestingMode = BacktestingMode.BAR,
        inverse: bool = False
    ):
        """"""
        self.mode = mode
        self.vt_symbol = vt_symbol
        self.interval = Interval(interval)
        self.rate = rate
        self.slippage = slippage
        self.size = size
        self.pricetick = pricetick
        self.start = start

        self.symbol, exchange_str = self.vt_symbol.split(".")
        self.exchange = Exchange(exchange_str)

        self.capital = capital
        self.end = end
        self.mode = mode
        self.inverse = inverse

    def add_strategy(self, strategy_class: type, setting: dict):
        """"""
        self.strategy_class = strategy_class
        self.strategy = strategy_class(
            self, strategy_class.__name__, self.vt_symbol, setting
        )

    def load_data(self):
        """"""
        self.output("开始加载历史数据")

        if not self.end:
            self.end = datetime.now()

        if self.start >= self.end:
            self.output("起始日期必须小于结束日期")
            return

        self.history_data.clear()       # Clear previously loaded history data

        # Load 30 days of data each time and allow for progress update
        progress_delta = timedelta(days=30)
        total_delta = self.end - self.start
        interval_delta = INTERVAL_DELTA_MAP[self.interval]

        start = self.start
        end = self.start + progress_delta
        progress = 0

        while start < self.end:
            end = min(end, self.end)  # Make sure end time stays within set range

            if self.mode == BacktestingMode.BAR:
                data = load_bar_data(
                    self.symbol,
                    self.exchange,
                    self.interval,
                    start,
                    end
                )
            else:
                data = load_tick_data(
                    self.symbol,
                    self.exchange,
                    start,
                    end
                )

            self.history_data.extend(data)

            progress += progress_delta / total_delta
            progress = min(progress, 1)
            progress_bar = "#" * int(progress * 10)
            self.output(f"加载进度：{progress_bar} [{progress:.0%}]")

            start = end + interval_delta
            end += (progress_delta + interval_delta)

        self.output(f"历史数据加载完成，数据量：{len(self.history_data)}")

    def run_backtesting(self):
        """"""
        if self.mode == BacktestingMode.BAR:
            func = self.new_bar
        else:
            func = self.new_tick

        self.strategy.on_init()

        # Use the first [days] of history data for initializing strategy
        day_count = 0
        ix = 0

        for ix, data in enumerate(self.history_data):
            if self.datetime and data.datetime.day != self.datetime.day:
                day_count += 1
                if day_count >= self.days:
                    break

            self.datetime = data.datetime
            self.callback(data)

        self.strategy.inited = True
        self.output("策略初始化完成")

        self.strategy.on_start()
        self.strategy.trading = True
        self.output("开始回放历史数据")

        # Use the rest of history data for running backtesting
        for data in self.history_data[ix:]:
            func(data)

        self.output("历史数据回放结束")

    def calculate_result(self):
        """"""
        self.output("开始计算逐日盯市盈亏")

        if not self.trades:
            self.output("成交记录为空，无法计算")
            return

        # Add trade data into daily reuslt.
        for trade in self.trades.values():
            d = trade.datetime.date()
            daily_result = self.daily_results[d]
            daily_result.add_trade(trade)

        # Calculate daily result by iteration.
        pre_close = 0
        start_pos = 0

        for daily_result in self.daily_results.values():
            daily_result.calculate_pnl(
                pre_close,
                start_pos,
                self.size,
                self.rate,
                self.slippage,
                self.inverse
            )

            pre_close = daily_result.close_price
            start_pos = daily_result.end_pos

        # Generate dataframe
        results = defaultdict(list)

        for daily_result in self.daily_results.values():
            for key, value in daily_result.__dict__.items():
                results[key].append(value)

        self.daily_df = DataFrame.from_dict(results).set_index("date")

        self.output("逐日盯市盈亏计算完成")
        return self.daily_df

    def calculate_statistics(self, df: DataFrame = None, output=True):
        """"""
        self.output("开始计算策略统计指标")

        # Check DataFrame input exterior
        if df is None:
            df = self.daily_df

        # Check for init DataFrame
        if df is None:
            # Set all statistics to 0 if no trade.
            start_date = ""
            end_date = ""
            total_days = 0
            profit_days = 0
            loss_days = 0
            end_balance = 0
            max_drawdown = 0
            max_ddpercent = 0
            max_drawdown_duration = 0
            total_net_pnl = 0
            daily_net_pnl = 0
            total_commission = 0
            daily_commission = 0
            total_slippage = 0
            daily_slippage = 0
            total_turnover = 0
            daily_turnover = 0
            total_trade_count = 0
            daily_trade_count = 0
            total_return = 0
            annual_return = 0
            daily_return = 0
            return_std = 0
            sharpe_ratio = 0
            return_drawdown_ratio = 0
        else:
            # Calculate balance related time series data
            df["balance"] = df["net_pnl"].cumsum() + self.capital
            df["return"] = np.log(df["balance"] / df["balance"].shift(1)).fillna(0)
            df["highlevel"] = (
                df["balance"].rolling(
                    min_periods=1, window=len(df), center=False).max()
            )
            df["drawdown"] = df["balance"] - df["highlevel"]
            df["ddpercent"] = df["drawdown"] / df["highlevel"] * 100

            # Calculate statistics value
            start_date = df.index[0]
            end_date = df.index[-1]

            total_days = len(df)
            profit_days = len(df[df["net_pnl"] > 0])
            loss_days = len(df[df["net_pnl"] < 0])

            end_balance = df["balance"].iloc[-1]
            max_drawdown = df["drawdown"].min()
            max_ddpercent = df["ddpercent"].min()
            max_drawdown_end = df["drawdown"].idxmin()
            max_drawdown_start = df["balance"][:max_drawdown_end].argmax()
            max_drawdown_duration = (max_drawdown_end - max_drawdown_start).days

            total_net_pnl = df["net_pnl"].sum()
            daily_net_pnl = total_net_pnl / total_days

            total_commission = df["commission"].sum()
            daily_commission = total_commission / total_days

            total_slippage = df["slippage"].sum()
            daily_slippage = total_slippage / total_days

            total_turnover = df["turnover"].sum()
            daily_turnover = total_turnover / total_days

            total_trade_count = df["trade_count"].sum()
            daily_trade_count = total_trade_count / total_days

            total_return = (end_balance / self.capital - 1) * 100
            annual_return = total_return / total_days * 240
            daily_return = df["return"].mean() * 100
            return_std = df["return"].std() * 100

            if return_std:
                sharpe_ratio = daily_return / return_std * np.sqrt(240)
            else:
                sharpe_ratio = 0

            return_drawdown_ratio = -total_return / max_ddpercent

        # Output
        if output:
            self.output("-" * 30)
            self.output(f"首个交易日：\t{start_date}")
            self.output(f"最后交易日：\t{end_date}")

            self.output(f"总交易日：\t{total_days}")
            self.output(f"盈利交易日：\t{profit_days}")
            self.output(f"亏损交易日：\t{loss_days}")

            self.output(f"起始资金：\t{self.capital:,.2f}")
            self.output(f"结束资金：\t{end_balance:,.2f}")

            self.output(f"总收益率：\t{total_return:,.2f}%")
            self.output(f"年化收益：\t{annual_return:,.2f}%")
            self.output(f"最大回撤: \t{max_drawdown:,.2f}")
            self.output(f"百分比最大回撤: {max_ddpercent:,.2f}%")
            self.output(f"最长回撤天数: \t{max_drawdown_duration}")

            self.output(f"总盈亏：\t{total_net_pnl:,.2f}")
            self.output(f"总手续费：\t{total_commission:,.2f}")
            self.output(f"总滑点：\t{total_slippage:,.2f}")
            self.output(f"总成交金额：\t{total_turnover:,.2f}")
            self.output(f"总成交笔数：\t{total_trade_count}")

            self.output(f"日均盈亏：\t{daily_net_pnl:,.2f}")
            self.output(f"日均手续费：\t{daily_commission:,.2f}")
            self.output(f"日均滑点：\t{daily_slippage:,.2f}")
            self.output(f"日均成交金额：\t{daily_turnover:,.2f}")
            self.output(f"日均成交笔数：\t{daily_trade_count}")

            self.output(f"日均收益率：\t{daily_return:,.2f}%")
            self.output(f"收益标准差：\t{return_std:,.2f}%")
            self.output(f"Sharpe Ratio：\t{sharpe_ratio:,.2f}")
            self.output(f"收益回撤比：\t{return_drawdown_ratio:,.2f}")

        statistics = {
            "start_date": start_date,
            "end_date": end_date,
            "total_days": total_days,
            "profit_days": profit_days,
            "loss_days": loss_days,
            "capital": self.capital,
            "end_balance": end_balance,
            "max_drawdown": max_drawdown,
            "max_ddpercent": max_ddpercent,
            "max_drawdown_duration": max_drawdown_duration,
            "total_net_pnl": total_net_pnl,
            "daily_net_pnl": daily_net_pnl,
            "total_commission": total_commission,
            "daily_commission": daily_commission,
            "total_slippage": total_slippage,
            "daily_slippage": daily_slippage,
            "total_turnover": total_turnover,
            "daily_turnover": daily_turnover,
            "total_trade_count": total_trade_count,
            "daily_trade_count": daily_trade_count,
            "total_return": total_return,
            "annual_return": annual_return,
            "daily_return": daily_return,
            "return_std": return_std,
            "sharpe_ratio": sharpe_ratio,
            "return_drawdown_ratio": return_drawdown_ratio,
        }

        return statistics

    def show_chart(self, df: DataFrame = None):
        """"""
        # Check DataFrame input exterior
        if df is None:
            df = self.daily_df

        # Check for init DataFrame
        if df is None:
            return

        plt.figure(figsize=(10, 16))

        balance_plot = plt.subplot(4, 1, 1)
        balance_plot.set_title("Balance")
        df["balance"].plot(legend=True)

        drawdown_plot = plt.subplot(4, 1, 2)
        drawdown_plot.set_title("Drawdown")
        drawdown_plot.fill_between(range(len(df)), df["drawdown"].values)

        pnl_plot = plt.subplot(4, 1, 3)
        pnl_plot.set_title("Daily Pnl")
        df["net_pnl"].plot(kind="bar", legend=False, grid=False, xticks=[])

        distribution_plot = plt.subplot(4, 1, 4)
        distribution_plot.set_title("Daily Pnl Distribution")
        df["net_pnl"].hist(bins=50)

        plt.show()


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
                endPrice = self.tick.lastPrice

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

            plt.show()

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


    def run_optimization(self, optimization_setting: OptimizationSetting, output=True):
        """"""
        # Get optimization setting and target
        settings = optimization_setting.generate_setting()
        target_name = optimization_setting.target_name

        if not settings:
            self.output("优化参数组合为空，请检查")
            return

        if not target_name:
            self.output("优化目标未设置，请检查")
            return

        # Use multiprocessing pool for running backtesting with different setting
        pool = multiprocessing.Pool(multiprocessing.cpu_count())

        results = []
        for setting in settings:
            result = (pool.apply_async(optimize, (
                target_name,
                self.strategy_class,
                setting,
                self.vt_symbol,
                self.interval,
                self.start,
                self.rate,
                self.slippage,
                self.size,
                self.pricetick,
                self.capital,
                self.end,
                self.mode,
                self.inverse
            )))
            results.append(result)

        pool.close()
        pool.join()

        # Sort results and output
        result_values = [result.get() for result in results]
        result_values.sort(reverse=True, key=lambda result: result[1])

        if output:
            for value in result_values:
                msg = f"参数：{value[0]}, 目标：{value[1]}"
                self.output(msg)

        return result_values

    def run_ga_optimization(self, optimization_setting: OptimizationSetting, population_size=100, ngen_size=30, output=True):
        """"""
        # Get optimization setting and target
        settings = optimization_setting.generate_setting_ga()
        target_name = optimization_setting.target_name

        if not settings:
            self.output("优化参数组合为空，请检查")
            return

        if not target_name:
            self.output("优化目标未设置，请检查")
            return

        # Define parameter generation function
        def generate_parameter():
            """"""
            return random.choice(settings)

        def mutate_individual(individual, indpb):
            """"""
            size = len(individual)
            paramlist = generate_parameter()
            for i in range(size):
                if random.random() < indpb:
                    individual[i] = paramlist[i]
            return individual,

        # Create ga object function
        global ga_target_name
        global ga_strategy_class
        global ga_setting
        global ga_vt_symbol
        global ga_interval
        global ga_start
        global ga_rate
        global ga_slippage
        global ga_size
        global ga_pricetick
        global ga_capital
        global ga_end
        global ga_mode
        global ga_inverse

        ga_target_name = target_name
        ga_strategy_class = self.strategy_class
        ga_setting = settings[0]
        ga_vt_symbol = self.vt_symbol
        ga_interval = self.interval
        ga_start = self.start
        ga_rate = self.rate
        ga_slippage = self.slippage
        ga_size = self.size
        ga_pricetick = self.pricetick
        ga_capital = self.capital
        ga_end = self.end
        ga_mode = self.mode
        ga_inverse = self.inverse

        # Set up genetic algorithem
        toolbox = base.Toolbox()
        toolbox.register("individual", tools.initIterate, creator.Individual, generate_parameter)
        toolbox.register("population", tools.initRepeat, list, toolbox.individual)
        toolbox.register("mate", tools.cxTwoPoint)
        toolbox.register("mutate", mutate_individual, indpb=1)
        toolbox.register("evaluate", ga_optimize)
        toolbox.register("select", tools.selNSGA2)

        total_size = len(settings)
        pop_size = population_size                      # number of individuals in each generation
        lambda_ = pop_size                              # number of children to produce at each generation
        mu = int(pop_size * 0.8)                        # number of individuals to select for the next generation

        cxpb = 0.95         # probability that an offspring is produced by crossover
        mutpb = 1 - cxpb    # probability that an offspring is produced by mutation
        ngen = ngen_size    # number of generation

        pop = toolbox.population(pop_size)
        hof = tools.ParetoFront()               # end result of pareto front

        stats = tools.Statistics(lambda ind: ind.fitness.values)
        np.set_printoptions(suppress=True)
        stats.register("mean", np.mean, axis=0)
        stats.register("std", np.std, axis=0)
        stats.register("min", np.min, axis=0)
        stats.register("max", np.max, axis=0)

        # Multiprocessing is not supported yet.
        # pool = multiprocessing.Pool(multiprocessing.cpu_count())
        # toolbox.register("map", pool.map)

        # Run ga optimization
        self.output(f"参数优化空间：{total_size}")
        self.output(f"每代族群总数：{pop_size}")
        self.output(f"优良筛选个数：{mu}")
        self.output(f"迭代次数：{ngen}")
        self.output(f"交叉概率：{cxpb:.0%}")
        self.output(f"突变概率：{mutpb:.0%}")

        start = time()

        algorithms.eaMuPlusLambda(
            pop,
            toolbox,
            mu,
            lambda_,
            cxpb,
            mutpb,
            ngen,
            stats,
            halloffame=hof
        )

        end = time()
        cost = int((end - start))

        self.output(f"遗传算法优化完成，耗时{cost}秒")

        # Return result list
        results = []

        for parameter_values in hof:
            setting = dict(parameter_values)
            target_value = ga_optimize(parameter_values)[0]
            results.append((setting, target_value, {}))

        return results

    def update_daily_close(self, price: float):
        """"""
        d = self.datetime.date()

        daily_result = self.daily_results.get(d, None)
        if daily_result:
            daily_result.close_price = price
        else:
            self.daily_results[d] = DailyResult(d, price)

    def new_bar(self, bar: BarData):
        """"""
        self.bar = bar
        self.datetime = bar.datetime

        self.cross_limit_order()
        self.cross_stop_order()
        self.strategy.on_bar(bar)

        self.update_daily_close(bar.close_price)

    def new_tick(self, tick: TickData):
        """"""
        self.tick = tick
        self.datetime = tick.datetime

        self.cross_limit_order()
        self.cross_stop_order()
        self.strategy.on_tick(tick)

        self.update_daily_close(tick.last_price)

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
                strategy.onOrder(order)

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
            if trade.vt_orderid in self.orderStrategyDict:
                strategy = self.orderStrategyDict[trade.vt_orderid]

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

    def load_bar(
        self,
        vt_symbol: str,
        days: int,
        interval: Interval,
        callback: Callable,
        use_database: bool
    ):
        """"""
        self.days = days
        self.callback = callback

    def load_tick(self, vt_symbol: str, days: int, callback: Callable):
        """"""
        self.days = days
        self.callback = callback

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

    def send_stop_order(
        self,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float
    ):
        """"""
        self.stop_order_count += 1

        stop_order = StopOrder(
            vt_symbol=self.vt_symbol,
            direction=direction,
            offset=offset,
            price=price,
            volume=volume,
            stop_orderid=f"{STOPORDER_PREFIX}.{self.stop_order_count}",
            strategy_name=self.strategy.strategy_name,
        )

        self.active_stop_orders[stop_order.stop_orderid] = stop_order
        self.stop_orders[stop_order.stop_orderid] = stop_order

        return stop_order.stop_orderid

    def send_limit_order(
        self,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float
    ):
        """"""
        self.limit_order_count += 1

        order = OrderData(
            symbol=self.symbol,
            exchange=self.exchange,
            orderid=str(self.limit_order_count),
            direction=direction,
            offset=offset,
            price=price,
            volume=volume,
            status=Status.SUBMITTING,
            gateway_name=self.gateway_name,
        )
        order.datetime = self.datetime

        self.active_limit_orders[order.vt_orderid] = order
        self.limit_orders[order.vt_orderid] = order

        return order.vt_orderid

    def cancel_order(self, strategy: CtaTemplate, vt_orderid: str):
        """
        Cancel order by vt_orderid.
        """
        if vt_orderid.startswith(STOPORDER_PREFIX):
            self.cancel_stop_order(strategy, vt_orderid)
        else:
            self.cancel_limit_order(strategy, vt_orderid)

    def cancel_stop_order(self, strategy: CtaTemplate, vt_orderid: str):
        """"""
        if vt_orderid not in self.active_stop_orders:
            return
        stop_order = self.active_stop_orders.pop(vt_orderid)

        stop_order.status = StopOrderStatus.CANCELLED
        self.strategy.on_stop_order(stop_order)

    def cancel_limit_order(self, strategy: CtaTemplate, vt_orderid: str):
        """"""
        if vt_orderid not in self.active_limit_orders:
            return
        order = self.active_limit_orders.pop(vt_orderid)

        order.status = Status.CANCELLED
        self.strategy.on_order(order)

    def cancel_all(self, strategy: CtaTemplate):
        """
        Cancel all orders, both limit and stop.
        """
        vt_orderids = list(self.active_limit_orders.keys())
        for vt_orderid in vt_orderids:
            self.cancel_limit_order(strategy, vt_orderid)

        stop_orderids = list(self.active_stop_orders.keys())
        for vt_orderid in stop_orderids:
            self.cancel_stop_order(strategy, vt_orderid)

    def write_log(self, msg: str, strategy: CtaTemplate = None):
        """
        Write log message.
        """
        msg = f"{self.datetime}\t{msg}"
        self.logs.append(msg)

    def send_email(self, msg: str, strategy: CtaTemplate = None):
        """
        Send email to default receiver.
        """
        pass

    def sync_strategy_data(self, strategy: CtaTemplate):
        """
        Sync strategy data into json file.
        """
        pass

    def get_engine_type(self):
        """
        Return engine type.
        """
        return self.engine_type

    def put_strategy_event(self, strategy: CtaTemplate):
        """
        Put an event to update strategy status.
        """
        pass

    def output(self, msg):
        """
        Output message of backtesting engine.
        """
        print(f"{datetime.now()}\t{msg}")

    def get_all_trades(self):
        """
        Return all trade data of current backtesting result.
        """
        return list(self.trades.values())

    def get_all_orders(self):
        """
        Return all limit order data of current backtesting result.
        """
        return list(self.limit_orders.values())

    def get_all_daily_results(self):
        """
        Return all daily result data.
        """
        return list(self.daily_results.values())


class DailyResult:
    """"""

    def __init__(self, date: date, close_price: float):
        """"""
        self.date = date
        self.close_price = close_price
        self.pre_close = 0

        self.trades = []
        self.trade_count = 0

        self.start_pos = 0
        self.end_pos = 0

        self.turnover = 0
        self.commission = 0
        self.slippage = 0

        self.trading_pnl = 0
        self.holding_pnl = 0
        self.total_pnl = 0
        self.net_pnl = 0

    def add_trade(self, trade: TradeData):
        """"""
        self.trades.append(trade)

    def calculate_pnl(
        self,
        pre_close: float,
        start_pos: float,
        size: int,
        rate: float,
        slippage: float,
        inverse: bool
    ):
        """"""
        # If no pre_close provided on the first day,
        # use value 1 to avoid zero division error
        if pre_close:
            self.pre_close = pre_close
        else:
            self.pre_close = 1

        # Holding pnl is the pnl from holding position at day start
        self.start_pos = start_pos
        self.end_pos = start_pos

        if not inverse:     # For normal contract
            self.holding_pnl = self.start_pos * \
                (self.close_price - self.pre_close) * size
        else:               # For crypto currency inverse contract
            self.holding_pnl = self.start_pos * \
                (1 / self.pre_close - 1 / self.close_price) * size

        # Trading pnl is the pnl from new trade during the day
        self.trade_count = len(self.trades)

        for trade in self.trades:
            if trade.direction == Direction.LONG:
                pos_change = trade.volume
            else:
                pos_change = -trade.volume

            self.end_pos += pos_change

            # For normal contract
            if not inverse:
                turnover = trade.volume * size * trade.price
                self.trading_pnl += pos_change * \
                    (self.close_price - trade.price) * size
                self.slippage += trade.volume * size * slippage
            # For crypto currency inverse contract
            else:
                turnover = trade.volume * size / trade.price
                self.trading_pnl += pos_change * \
                    (1 / trade.price - 1 / self.close_price) * size
                self.slippage += trade.volume * size * slippage / (trade.price ** 2)

            self.turnover += turnover
            self.commission += turnover * rate

        # Net pnl takes account of commission and slippage cost
        self.total_pnl = self.trading_pnl + self.holding_pnl
        self.net_pnl = self.total_pnl - self.commission - self.slippage


def optimize(
    target_name: str,
    strategy_class: CtaTemplate,
    setting: dict,
    vt_symbol: str,
    interval: Interval,
    start: datetime,
    rate: float,
    slippage: float,
    size: float,
    pricetick: float,
    capital: int,
    end: datetime,
    mode: BacktestingMode,
    inverse: bool
):
    """
    Function for running in multiprocessing.pool
    """
    engine = BacktestingEngine()

    engine.set_parameters(
        vt_symbol=vt_symbol,
        interval=interval,
        start=start,
        rate=rate,
        slippage=slippage,
        size=size,
        pricetick=pricetick,
        capital=capital,
        end=end,
        mode=mode,
        inverse=inverse
    )

    engine.add_strategy(strategy_class, setting)
    engine.load_data()
    engine.run_backtesting()
    engine.calculate_result()
    statistics = engine.calculate_statistics(output=False)

    target_value = statistics[target_name]
    return (str(setting), target_value, statistics)


@lru_cache(maxsize=1000000)
def _ga_optimize(parameter_values: tuple):
    """"""
    setting = dict(parameter_values)

    result = optimize(
        ga_target_name,
        ga_strategy_class,
        setting,
        ga_vt_symbol,
        ga_interval,
        ga_start,
        ga_rate,
        ga_slippage,
        ga_size,
        ga_pricetick,
        ga_capital,
        ga_end,
        ga_mode,
        ga_inverse
    )
    return (result[1],)


def ga_optimize(parameter_values: list):
    """"""
    return _ga_optimize(tuple(parameter_values))


@lru_cache(maxsize=999)
def load_bar_data(
    symbol: str,
    exchange: Exchange,
    interval: Interval,
    start: datetime,
    end: datetime
):
    """"""
    return database_manager.load_bar_data(
        symbol, exchange, interval, start, end
    )


@lru_cache(maxsize=999)
def load_tick_data(
    symbol: str,
    exchange: Exchange,
    start: datetime,
    end: datetime
):
    """"""
    return database_manager.load_tick_data(
        symbol, exchange, start, end
    )


# GA related global value
ga_end = None
ga_mode = None
ga_target_name = None
ga_strategy_class = None
ga_setting = None
ga_vt_symbol = None
ga_interval = None
ga_start = None
ga_rate = None
ga_slippage = None
ga_size = None
ga_pricetick = None
ga_capital = None



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

