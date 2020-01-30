# encoding: UTF-8
'''
本文件中包含的是CTA模块的回测引擎，回测引擎的API和CTA引擎一致，
可以使用和实盘相同的代码进行回测。
'''
from __future__ import division

from datetime import datetime, timedelta
from collections import OrderedDict
from itertools import product
import multiprocessing
import copy
from itertools import groupby
import traceback

import pymongo

try:
    import pandas as pd
except ImportError:
    pass

import numpy as np
#import matplotlib.pyplot as plt

# 如果安装了seaborn则设置为白色风格
try:
    import seaborn as sns
    sns.set_style('whitegrid')
except ImportError:
    pass

from vnpy.trader.vtGlobal import globalSetting

from vnpy.trader.vtFunction import loadMongoSetting
from vnpy.trader.vtFunction import isRecordingTime, isTradingTime, timeit
import logging

MINUTE_DB_NAME = 'VnTrader_1Min_Db'
#----------------------------------------------------------------------
# from .caching import Cache
from pymongo import ASCENDING

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

########################################################################
class BacktestingEngine(object):
    """
    CTA回测引擎
    函数接口和策略引擎保持一样，
    从而实现同一套代码从回测到实盘。
    """

    TICK_MODE = 'tick'
    BAR_MODE = 'bar'

    #----------------------------------------------------------------------
    def __init__(self):
        """Constructor"""
        # 本地停止单
        self.stopOrderCount = 0  # 编号计数：stopOrderID = STOPORDERPREFIX + str(stopOrderCount)

        # 本地停止单字典, key为stopOrderID，value为stopOrder对象
        self.stopOrderDict = {}  # 停止单撤销后不会从本字典中删除
        self.workingStopOrderDict = {}  # 停止单撤销后会从本字典中删除

        self.engineType = EngineType.BACKTESTING  # 引擎类型为回测

        self.strategy = None  # 回测策略
        self.mode = self.BAR_MODE  # 回测模式，默认为K线

        self.startDate = ''
        self.initDays = 0
        self.endDate = ''

        self.capital = 1000000  # 回测时的起始本金（默认100万）
        self.slippage = 0  # 回测时假设的滑点
        self.rate = 0  # 回测时假设的佣金比例（适用于百分比佣金）
        self.size = 1  # 合约大小，默认为1
        self.priceTick = 1.0  # 价格最小变动

        self.dbName = ''  # 回测数据库名
        self.symbol = ''  # 回测集合名
        self.dbCursor = []

        self.dataStartDate = None  # 回测数据开始日期，datetime对象
        self.dataEndDate = None  # 回测数据结束日期，datetime对象
        self.strategyStartDate = None  # 策略启动日期（即前面的数据用于初始化），datetime对象

        self.limitOrderCount = 0  # 限价单编号
        self.limitOrderDict = OrderedDict()  # 限价单字典
        self.workingLimitOrderDict = OrderedDict()  # 活动限价单字典，用于进行撮合用

        # 保存策略名称和委托号列表的字典
        # key为name，value为保存orderID（限价+本地停止）的集合
        self.strategyOrderDict = {}

        self.tradeCount = 0  # 成交编号
        self.tradeDict = OrderedDict()  # 成交字典

        self.logList = []  # 日志记录

        # 当前最新数据，用于模拟成交用
        self.tick = None
        self.bar = None
        self.dt = None  # 最新的时间

        # 日线回测结果计算用
        self.dailyResultDict = OrderedDict()

        # 保存vtOrderID和strategy对象映射的字典（用于推送order和trade数据）
        # key为vtOrderID，value为strategy对象
        self.orderStrategyDict = {}

        # 保存策略实例的字典
        # key为策略名称，value为策略实例，注意策略名称不允许重复
        self.strategyDict = {}

        # 清算结果
        self.liquidation = OrderedDict()

    #------------------------------------------------
    # 通用功能
    #------------------------------------------------

    #----------------------------------------------------------------------
    def roundToPriceTick(self, price):
        """取整价格到合约最小价格变动"""
        if not self.priceTick:
            return price

        newPrice = round(price / self.priceTick, 0) * self.priceTick
        return newPrice

    #----------------------------------------------------------------------
    def output(self, content):
        """输出内容"""
        print(content)
        logging.info(content)

    #------------------------------------------------
    # 参数设置相关
    #------------------------------------------------

    #----------------------------------------------------------------------
    def setStartDate(self, startDate='20100416', initDays=10):
        """设置回测的启动日期"""
        self.startDate = startDate
        self.initDays = initDays

        self.dataStartDate = datetime.strptime(startDate, '%Y%m%d')

        initTimeDelta = timedelta(initDays)
        self.strategyStartDate = self.dataStartDate + initTimeDelta

    #----------------------------------------------------------------------
    def setEndDate(self, endDate=''):
        """设置回测的结束日期"""
        self.endDate = endDate

        if endDate:
            self.dataEndDate = datetime.strptime(endDate, '%Y%m%d')

            # 若不修改时间则会导致不包含dataEndDate当天数据
            self.dataEndDate = self.dataEndDate.replace(hour=23, minute=59)

    #----------------------------------------------------------------------
    def setBacktestingMode(self, mode):
        """设置回测模式"""
        self.mode = mode

    #----------------------------------------------------------------------
    def setDatabase(self, dbName, symbol):
        """设置历史数据所用的数据库"""
        self.dbName = dbName
        self.symbol = symbol

    #----------------------------------------------------------------------
    def setCapital(self, capital):
        """设置资本金"""
        self.capital = capital

    #----------------------------------------------------------------------
    def setSlippage(self, slippage):
        """设置滑点点数"""
        self.slippage = slippage

    #----------------------------------------------------------------------
    def setSize(self, size):
        """设置合约大小"""
        self.size = size

    #----------------------------------------------------------------------
    def setRate(self, rate):
        """设置佣金比例"""
        self.rate = rate

    #----------------------------------------------------------------------
    def setPriceTick(self, priceTick):
        """设置价格最小变动"""
        self.priceTick = priceTick

    def get_engine_type(self):
        """"""
        return self.engineType

    #------------------------------------------------
    # 数据回放相关
    #------------------------------------------------

    #----------------------------------------------------------------------
    # @Cache(ttl=60 * 60 * 24, maxsize=1024*1024, filepath='./temp/cache')
    def dbQuery(self, dbName, collectionName, d):
        """从MongoDB中读取数据，d是查询要求，返回的是数据库查询的指针"""

        sortKey = ''
        sortDirection = ASCENDING

        host, port, logging = loadMongoSetting()
        dbClient = pymongo.MongoClient(host, port)

        if dbClient:
            db = dbClient[dbName]
            collection = db[collectionName]

            if sortKey:
                cursor = collection.find(d).sort(sortKey,
                                                 sortDirection)  # 对查询出来的数据进行排序
            else:
                cursor = collection.find(d)

            if cursor:
                return list(cursor)
            else:
                return []
        else:
            return []

    #----------------------------------------------------------------------
    @timeit
    def runBacktesting(self, symbols = None):
        for i in self.nextTime(symbols if symbols else [self.symbol]):
            pass

    #----------------------------------------------------------------------
    def nextTime(self, symbols):
        """数据源按时间进行同步推送"""
        iterators = []
        for s in symbols:
            iterators.append(self.steps(s))

        # 初始化开始时间
        datetime = next(iterators[0])

        while True:
            for iterator in iterators:
                # 时间前进
                while next(iterator) < datetime:
                    pass

                yield
                datetime = next(iterator)

    #----------------------------------------------------------------------
    def steps(self, symbol):
        """运行回测"""

        # 载入历史数据
        if not self.dataEndDate:
            flt = {'datetime': {'$gte': self.strategyStartDate}}  # 数据过滤条件
        else:
            flt = {
                'datetime': {
                    '$gte': self.strategyStartDate,
                    '$lte': self.dataEndDate
                }
            }

        # 初始化时间
        yield self.strategyStartDate

        dbCursor = None  # 数据库指针

        if self.mode == self.BAR_MODE and (
             (self.dataEndDate if self.dataEndDate else datetime.today()) - self.strategyStartDate).days <= 200:
            # bar数据使用Cache方法，以便本地快速回测
            #dbCursor = collection.find(flt)#.sort('datetime')
            dbCursor = self.dbQuery(self.dbName, symbol, flt)
            # fix: for show
            self.dbCursor.extend(dbCursor)
            self.output(str(flt))
            self.output(u'载入完成，数据量：%s' % (len(dbCursor)))
        else:
            # tick数据使用db curse，减小数据服务器压力
            self.dbClient = pymongo.MongoClient(globalSetting['mongoHost'],
                                                globalSetting['mongoPort'])
            collection = self.dbClient[self.dbName][symbol]
            self.output(u'开始载入数据')
            dbCursor = collection.find(flt,batch_size=1000)  #.sort('datetime')
            self.output(str(flt))
            self.output(u'载入完成，数据量：%s' % (dbCursor.count()))

        # 首先根据回测模式，确认要使用的数据类
        if self.mode == self.BAR_MODE:
            dataClass = BarData
            func = self.newBar
        else:
            dataClass = TickData
            func = self.newTick

        # 如果有回测结果，则不再回测
        if len(self.strategy.persistent):
            self.tradeDict = self.strategy.persistent
            func = self.lazy
            self.output(u'使用缓存交易结果')

        self.output(u'开始回测')

        self.strategy.inited = True
        self.strategy.onInit()
        self.output(u'策略初始化完成')

        self.strategy.trading = True
        self.strategy.onStart()
        self.output(u'策略启动完成')

        self.output(u'开始回放数据')

        lastData = None
        spreadAdjust = 0

        for d in dbCursor:
            data = dataClass()
            if 'exchange' not in d:
                d['exchange'] = "SHFE"
            data.__dict__ = d
            if not isRecordingTime(data.datetime) or not isTradingTime(
                    data.datetime.time()):
                RED = '\x1b[91m'
                ENDC = '\x1b[0m'
                self.writeCtaLog(
                    u'非交易时间区数据: %s %s %s' % (RED, data.datetime, ENDC))
            else:

                # 在指标计算的价格buffer中进行左侧价差调整
                # if lastBar and abs(data.openInterest - lastBar.openInterest)/data.openInterest > 0.01 and data.datetime.minute == 0 and data.close - lastBar.close < 0:
                #     spreadAdjust = data.close - lastBar.close
                #     print("left price spread adjust: ", data.datetime, spreadAdjust)

                if spreadAdjust < 0:
                    spreadAdjust += 1
                    if spreadAdjust > 0:
                        spreadAdjust = 0

                    data.open_price -= spreadAdjust
                    data.close_price -= spreadAdjust
                    data.high_price -= spreadAdjust
                    data.low_price -= spreadAdjust

                #  如果换月，所有策略平仓
                if lastData and (data.openInterest - lastData.openInterest)/lastData.openInterest > 0.005:
                    #平仓
                    if self.mode == self.BAR_MODE:
                        spreadAdjust = data.close - lastData.close
                        if abs(spreadAdjust) / data.close < 0.01:
                            spreadAdjust = 0
                    else:
                        spreadAdjust = data.lastPrice - lastData.lastPrice
                        if abs(spreadAdjust) / data.lastPrice < 0.01:
                            spreadAdjust = 0

                    if abs(spreadAdjust) > 0:
                        print("main contract change: ", data.datetime, spreadAdjust)
                        data.leftPriceAdjust = spreadAdjust #加入价差调整标志
                        for strategy in self.strategyDict.values():
                            strategy.clearOrder()

                if lastData:
                    func(lastData)
                    

                #func(data)
                lastData = data

            yield data.datetime

        self.output(u'数据回放结束')

    #----------------------------------------------------------------------
    def lazy(self, bar):
        """不计算策略"""
        self.bar = bar
        self.dt = bar.datetime
        self.updateDailyClose(bar.datetime, bar.close)

    #----------------------------------------------------------------------
    def newBar(self, bar):
        """新的K线"""
        self.bar = bar
        self.dt = bar.datetime

        self.crossLimitOrder()  # 先撮合限价单
        self.crossStopOrder()  # 再撮合停止单
        self.strategy.on_bar(bar)  # 推送K线到策略中

        self.updateDailyClose(bar.datetime, bar.close)

    #----------------------------------------------------------------------
    def newTick(self, tick):
        """新的Tick"""
        self.tick = tick
        self.dt = tick.datetime

        self.crossLimitOrder()
        self.crossStopOrder()
        self.strategy.on_tick(tick)

        self.updateDailyClose(tick.datetime, tick.lastPrice)

    #----------------------------------------------------------------------
    def initStrategy(self, strategyClass, setting=None):
        """
        初始化策略
        setting是策略的参数设置，如果使用类中写好的默认设置则可以不传该参数
        """
        self.strategy = strategyClass(self, setting)
        self.strategy.name = self.strategy.className

    #----------------------------------------------------------------------
    def crossLimitOrder(self):
        """基于最新数据撮合限价单"""
        # 先确定会撮合成交的价格
        if self.mode == self.BAR_MODE:
            buyCrossPrice = self.bar.low  # 若买入方向限价单价格高于该价格，则会成交
            sellCrossPrice = self.bar.high  # 若卖出方向限价单价格低于该价格，则会成交
            buyBestCrossPrice = self.bar.open  # 在当前时间点前发出的买入委托可能的最优成交价
            sellBestCrossPrice = self.bar.open  # 在当前时间点前发出的卖出委托可能的最优成交价
            vtSymbol = self.bar.vtSymbol
        else:
            buyCrossPrice = self.tick.askPrice1
            sellCrossPrice = self.tick.bidPrice1
            buyBestCrossPrice = self.tick.askPrice1
            sellBestCrossPrice = self.tick.bidPrice1
            vtSymbol = self.tick.vtSymbol

        # 遍历限价单字典中的所有限价单
        for orderID, order in list(self.workingLimitOrderDict.items()):
            # 推送委托进入队列（未成交）的状态更新
            if not order.status:
                order.status = Status.NOTTRADED
                strategy = self.orderStrategyDict[order.orderID]
                strategy.onOrder(order)

            # 判断是否会成交
            buyCross = (
                order.direction == Direction.LONG
                and order.price >= buyCrossPrice
                and vtSymbol.lower() == order.vtSymbol.lower()
                and buyCrossPrice > 0)  # 国内的tick行情在涨停时askPrice1为0，此时买无法成交

            sellCross = (
                order.direction == Direction.SHORT
                and order.price <= sellCrossPrice
                and vtSymbol.lower() == order.vtSymbol.lower()
                and sellCrossPrice > 0)  # 国内的tick行情在跌停时bidPrice1为0，此时卖无法成交

            # 如果发生了成交
            if buyCross or sellCross:
                # 推送成交数据
                self.tradeCount += 1  # 成交编号自增1
                tradeID = str(self.tradeCount)
                trade = TradeData()
                trade.vtSymbol = order.vtSymbol
                trade.tradeID = tradeID
                trade.vtTradeID = tradeID
                trade.orderID = order.orderID
                trade.vtOrderID = order.orderID
                trade.direction = order.direction
                trade.offset = order.offset

                #增加多策略测试
                # 将成交推送到策略对象中
                if trade.vtOrderID in self.orderStrategyDict:
                    strategy = self.orderStrategyDict[trade.vtOrderID]

                # 以买入为例：
                # 1. 假设当根K线的OHLC分别为：100, 125, 90, 110
                # 2. 假设在上一根K线结束(也是当前K线开始)的时刻，策略发出的委托为限价105
                # 3. 则在实际中的成交价会是100而不是105，因为委托发出时市场的最优价格是100
                if buyCross:
                    trade.price = min(order.price, buyBestCrossPrice)
                    strategy.pos += order.totalVolume
                else:
                    trade.price = max(order.price, sellBestCrossPrice)
                    strategy.pos -= order.totalVolume

                trade.volume = order.totalVolume
                trade.tradeTime = str(self.dt)
                trade.dt = self.dt
                #add trade strategy name, 以便于区别多策略混合效果
                trade.name = strategy.name

                strategy.onTrade(trade)

                self.tradeDict[tradeID] = trade

                # 推送委托数据
                order.tradedVolume = order.totalVolume
                order.status = STATUS_ALLTRADED
                strategy.onOrder(order)

                # 从字典中删除该限价单
                if orderID in self.workingLimitOrderDict:
                    del self.workingLimitOrderDict[orderID]

    #----------------------------------------------------------------------
    def crossStopOrder(self):
        """基于最新数据撮合停止单"""
        # 先确定会撮合成交的价格，这里和限价单规则相反
        if self.mode == self.BAR_MODE:
            buyCrossPrice = self.bar.high  # 若买入方向停止单价格低于该价格，则会成交
            sellCrossPrice = self.bar.low  # 若卖出方向限价单价格高于该价格，则会成交
            bestCrossPrice = self.bar.open  # 最优成交价，买入停止单不能低于，卖出停止单不能高于
            vtSymbol = self.bar.vtSymbol
        else:
            buyCrossPrice = self.tick.lastPrice
            sellCrossPrice = self.tick.lastPrice
            bestCrossPrice = self.tick.lastPrice
            vtSymbol = self.tick.vtSymbol

        # 遍历停止单字典中的所有停止单
        for stopOrderID, so in list(self.workingStopOrderDict.items()):
            # 判断是否会成交
            buyCross = so.direction == DIRECTION_LONG and so.price <= buyCrossPrice and vtSymbol.lower(
            ) == so.vtSymbol.lower()
            sellCross = so.direction == DIRECTION_SHORT and so.price >= sellCrossPrice and vtSymbol.lower(
            ) == so.vtSymbol.lower()

            # 如果发生了成交
            if buyCross or sellCross:
                # 更新停止单状态，并从字典中删除该停止单
                so.status = STOPORDER_TRIGGERED
                if stopOrderID in self.workingStopOrderDict:
                    del self.workingStopOrderDict[stopOrderID]

                # 推送成交数据
                self.tradeCount += 1  # 成交编号自增1
                tradeID = str(self.tradeCount)
                trade = TradeData()
                trade.vtSymbol = so.vtSymbol
                trade.tradeID = tradeID
                trade.vtTradeID = tradeID

                if buyCross:
                    so.strategy.pos += so.volume
                    trade.price = max(bestCrossPrice, so.price)
                else:
                    so.strategy.pos -= so.volume
                    trade.price = min(bestCrossPrice, so.price)

                self.limitOrderCount += 1
                orderID = str(self.limitOrderCount)
                trade.orderID = orderID
                trade.vtOrderID = orderID
                trade.direction = so.direction
                trade.offset = so.offset
                trade.volume = so.volume
                trade.tradeTime = str(self.dt)
                trade.dt = self.dt
                #add trade strategy name, 以便于区别多策略混合效果
                trade.name = so.strategy.name

                self.tradeDict[tradeID] = trade

                # 推送委托数据
                order = OrderData()
                order.vtSymbol = so.vtSymbol
                order.symbol = so.vtSymbol
                order.orderID = orderID
                order.vtOrderID = orderID
                order.direction = so.direction
                order.offset = so.offset
                order.price = so.price
                order.totalVolume = so.volume
                order.tradedVolume = so.volume
                order.status = STATUS_ALLTRADED
                order.orderTime = trade.tradeTime

                self.limitOrderDict[orderID] = order

                # 按照顺序推送数据
                so.strategy.onStopOrder(so)
                so.strategy.onOrder(order)
                so.strategy.onTrade(trade)

    #------------------------------------------------
    # 策略接口相关
    #------------------------------------------------


    #----------------------------------------------------------------------
    def sendOrderRaw(self, vtSymbol, direction, offset, price, volume, strategy):
        """发单"""
        if not strategy:
            strategy = self.strategy

        self.limitOrderCount += 1
        orderID = str(self.limitOrderCount)

        order = OrderData()
        order.vtSymbol = vtSymbol
        order.price = self.roundToPriceTick(price)
        order.totalVolume = volume
        order.orderID = orderID
        order.vtOrderID = orderID
        order.orderTime = str(self.dt)

        order.direction = direction
        order.offset = offset

        # 保存到限价单字典中
        self.workingLimitOrderDict[orderID] = order
        self.limitOrderDict[orderID] = order

        # 保存orderID到策略委托号集合中
        if not strategy.name in self.strategyOrderDict.keys():
            self.strategyOrderDict[strategy.name] = set()
        self.strategyOrderDict[strategy.name].add(orderID)

        self.orderStrategyDict[orderID] = strategy  # 保存vtOrderID和策略的映射关系
        self.strategyDict[strategy.name] = strategy

        return [orderID]

    #----------------------------------------------------------------------
    def sendOrder(self, vtSymbol, orderType, price, volume, strategy):
        """发单"""
        self.limitOrderCount += 1
        orderID = str(self.limitOrderCount)

        order = OrderData()
        order.vtSymbol = vtSymbol
        order.price = self.roundToPriceTick(price)
        order.totalVolume = volume
        order.orderID = orderID
        order.vtOrderID = orderID
        order.orderTime = str(self.dt)

        # CTA委托类型映射
        if orderType == CTAORDER_BUY:
            order.direction = DIRECTION_LONG
            order.offset = OFFSET_OPEN
        elif orderType == CTAORDER_SELL:
            order.direction = DIRECTION_SHORT
            order.offset = OFFSET_CLOSE
        elif orderType == CTAORDER_SHORT:
            order.direction = DIRECTION_SHORT
            order.offset = OFFSET_OPEN
        elif orderType == CTAORDER_COVER:
            order.direction = DIRECTION_LONG
            order.offset = OFFSET_CLOSE

        # 保存到限价单字典中
        self.workingLimitOrderDict[orderID] = order
        self.limitOrderDict[orderID] = order

        # 保存orderID到策略委托号集合中
        if not strategy.name in self.strategyOrderDict.keys():
            self.strategyOrderDict[strategy.name] = set()
        self.strategyOrderDict[strategy.name].add(orderID)

        self.orderStrategyDict[orderID] = strategy  # 保存vtOrderID和策略的映射关系
        self.strategyDict[strategy.name] = strategy

        return [orderID]

    #----------------------------------------------------------------------
    def cancelOrder(self, vtOrderID):
        """撤单"""
        if vtOrderID in self.workingLimitOrderDict:
            order = self.workingLimitOrderDict[vtOrderID]

            order.status = STATUS_CANCELLED
            order.cancelTime = self.dt.strftime('%H:%M:%S')

            strategy = self.orderStrategyDict[order.orderID]
            strategy.onOrder(order)

            del self.workingLimitOrderDict[vtOrderID]

    #----------------------------------------------------------------------
    def sendStopOrder(self, vtSymbol, orderType, price, volume, strategy):
        """发停止单（本地实现）"""
        self.stopOrderCount += 1
        stopOrderID = STOPORDERPREFIX + str(self.stopOrderCount)

        so = StopOrder()
        so.vtSymbol = vtSymbol
        so.price = self.roundToPriceTick(price)
        so.volume = volume
        so.strategy = strategy
        so.status = STOPORDER_WAITING
        so.stopOrderID = stopOrderID

        if orderType == CTAORDER_BUY:
            so.direction = DIRECTION_LONG
            so.offset = OFFSET_OPEN
        elif orderType == CTAORDER_SELL:
            so.direction = DIRECTION_SHORT
            so.offset = OFFSET_CLOSE
        elif orderType == CTAORDER_SHORT:
            so.direction = DIRECTION_SHORT
            so.offset = OFFSET_OPEN
        elif orderType == CTAORDER_COVER:
            so.direction = DIRECTION_LONG
            so.offset = OFFSET_CLOSE

        # 保存stopOrder对象到字典中
        self.stopOrderDict[stopOrderID] = so
        self.workingStopOrderDict[stopOrderID] = so

        # 保存stopOrderID到策略委托号集合中
        if not strategy.name in self.strategyOrderDict.keys():
            self.strategyOrderDict[strategy.name] = set()
        self.strategyOrderDict[strategy.name].add(stopOrderID)
        self.strategyDict[strategy.name] = strategy

        # 推送停止单初始更新
        so.strategy.onStopOrder(so)

        return [stopOrderID]

    #----------------------------------------------------------------------
    def cancelStopOrder(self, stopOrderID):
        """撤销停止单"""
        # 检查停止单是否存在
        if stopOrderID in self.workingStopOrderDict:
            so = self.workingStopOrderDict[stopOrderID]
            so.status = STOPORDER_CANCELLED
            del self.workingStopOrderDict[stopOrderID]
            so.strategy.onStopOrder(so)

            # 从策略委托号集合中移除
            s = self.strategyOrderDict[so.strategy.name]
            if stopOrderID in s:
                s.remove(stopOrderID)

    #----------------------------------------------------------------------
    def putStrategyEvent(self, name):
        """发送策略更新事件，回测中忽略"""
        pass

    #----------------------------------------------------------------------
    def insertData(self, dbName, collectionName, data):
        """考虑到回测中不允许向数据库插入数据，防止实盘交易中的一些代码出错"""
        pass

    #----------------------------------------------------------------------
    def loadBar(self, dbName, collectionName, days):
        # """直接返回初始化数据列表中的Bar"""
        """载入历史数据"""

        if days == 0:
            return []

        self.output(u'开始载入%s天数据' % str(days))
        # 载入初始化需要用的数据
        flt = {
            'datetime': {
                '$gte': self.strategyStartDate - timedelta(days),
                '$lt': self.strategyStartDate
            }
        }

        initCursor = self.dbQuery(MINUTE_DB_NAME, collectionName, flt)
        #self.output(str(flt))
        self.output(u'载入完成，数据量：%s' % (len(initCursor)))

        initData = []
        for d in initCursor:
            #data = dataClass()
            data = BarData()
            if 'exchange' not in d:
                d['exchange'] = "SHFE"
            data.__dict__ = d
            if not isRecordingTime(data.datetime) or not isTradingTime(
                    data.datetime.time()):
                RED = '\x1b[91m'
                ENDC = '\x1b[0m'
                self.writeCtaLog(
                    u'非交易时间区数据: %s %s %s' % (RED, data.datetime, ENDC))
            else:
                initData.append(data)

        return initData

    #----------------------------------------------------------------------
    def loadTick(self, dbName, collectionName, startDate):
        """直接返回初始化数据列表中的Tick"""
        return []

    #----------------------------------------------------------------------
    def writeCtaLog(self, content, level='info'):
        """记录日志"""
        log = str(self.dt) + "\t" + content
        #print(log)
        #self.logList.append(log)

        # 写入本地log日志
        if level == 'info':
            logging.info(log)
        elif level == 'debug':
            logging.debug(log)
        elif level == 'warning':
            logging.warn(log)
        elif level == 'critical':
            logging.critical(log)

    def writeCtaLog1(self, content, static_var=["tag", 0, 0, 0]):
        """记录日志"""
        log = str(self.dt) + "\t" + content
        if not static_var[0] == content[0:4] or not static_var[1] == len(
                content):
            print('.' * static_var[2])
            print(log)
            static_var[2] = 0

        static_var[0] = content[0:4]
        static_var[1] = len(content)
        static_var[2] += 1

        self.logList.append(log)

    #----------------------------------------------------------------------
    def cancelAll(self, name):
        """全部撤单"""
        # # 撤销限价单
        # for orderID in self.workingLimitOrderDict.keys():
        #     self.cancelOrder(orderID)

        # # 撤销停止单
        # for stopOrderID in self.workingStopOrderDict.keys():
        #     self.cancelStopOrder(stopOrderID)

        if not name in self.strategyOrderDict.keys():
            return

        s = self.strategyOrderDict[name]

        # 遍历集合，全部撤单
        # 这里不能直接遍历集合s，因为撤单时会修改s中的内容，导致出错
        for orderID in list(s):
            if STOPORDERPREFIX in orderID:
                self.cancelStopOrder(orderID)
            else:
                self.cancelOrder(orderID)

        s.clear()

    #------------------------------------------------
    # 结果计算相关
    #------------------------------------------------
    #----------------------------------------------------------------------
    def calculateBacktestingResult(self):
        return self.calculateBacktestingResultImp(self.tradeDict.values())

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
                elif trade.direction == DIRECTION_LONG:
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
                                    entryTrade.price, entryTrade.dt,
                                    exitTrade.price, exitTrade.dt,
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
                                    entryTrade.price, entryTrade.dt,
                                    exitTrade.price, exitTrade.dt,
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
            if self.mode == self.BAR_MODE:
                endPrice = self.bar.close
            else:
                endPrice = self.tick.lastPrice

            for trade in longTrade:
                result = TradingResult(trade.price, trade.dt, endPrice,
                                       self.dt, trade.volume, self.rate,
                                       self.slippage, self.size, key)
                resultList.append(result)
                longTradeList.append(result.pnl)  # 加入空头交易

                #添加结束交易，确保按日统计的准确性
                t = TradeData()
                t.offset = DIRECTION_SHORT
                t.volume = trade.volume
                t.price = endPrice
                t.tradeTime = str(self.dataEndDate)
                t.dt = self.dataEndDate
                if not self.dataEndDate:
                    t.dt = datetime.now()
                t.name = trade.name
                #每个交易策略只会做一次清算
                self.liquidation[trade.name] = t

            for trade in shortTrade:
                result = TradingResult(trade.price, trade.dt, endPrice,
                                       self.dt, -trade.volume, self.rate,
                                       self.slippage, self.size, key)
                resultList.append(result)
                shortTradeList.append(result.pnl)  # 加入多头交易
                

                #添加结束交易，确保按日统计的准确性
                t = TradeData()
                t.offset = DIRECTION_LONG
                t.volume = trade.volume
                t.price = endPrice
                t.tradeTime = str(self.dataEndDate)
                t.dt = self.dataEndDate
                if not self.dataEndDate:
                    t.dt = datetime.now()
                t.name = trade.name
                #每个交易策略只会做一次清算
                self.liquidation[trade.name] = t

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
                sorted(self.tradeDict.values(), key=lambda t: t.name),
                lambda t: t.name):
            self.showBacktestingResultImp(list(items))

        return self.showBacktestingResultImp(list(self.tradeDict.values()))

    #----------------------------------------------------------------------
    def showBacktestingResultImp(self, tradearray):
        """显示回测结果"""
        d = self.calculateBacktestingResultImp(tradearray)
        if not d or not d['timeList']:
            return

        trueTimeDelta = (365. / ((self.dataEndDate - self.dataStartDate).days + 1)) if self.dataEndDate else \
                        (365. / ((d['timeList'][-1] - self.dataStartDate).days + 1))
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

    #----------------------------------------------------------------------
    def clearBacktestingResult(self):
        """清空之前回测的结果"""
        # 清空限价单相关
        self.limitOrderCount = 0
        self.limitOrderDict.clear()
        self.workingLimitOrderDict.clear()

        # 清空停止单相关
        self.stopOrderCount = 0
        self.stopOrderDict.clear()
        self.workingStopOrderDict.clear()

        # 清空成交相关
        self.tradeCount = 0
        self.tradeDict.clear()

        # 清空 日线回测结果
        self.dailyResultDict = OrderedDict()
        # 清空 vtOrderID和strategy对象映射的字典（用于推送order和trade数据）
        self.orderStrategyDict = {}
        # 清空 策略实例的字典
        self.strategyDict = {}
        # 清空 清算结果
        self.liquidation = OrderedDict()

    #----------------------------------------------------------------------
    def runOptimization(self, strategyClass, optimizationSetting):
        """优化参数"""
        # 获取优化设置
        settingList = optimizationSetting.generateSetting()
        targetName = optimizationSetting.optimizeTarget

        # 检查参数设置问题
        if not settingList or not targetName:
            self.output(u'优化设置有问题，请检查')

        # 遍历优化
        resultList = []
        for setting in settingList:
            self.clearBacktestingResult()
            self.output('-' * 30)
            self.output('setting: %s' % str(setting))
            self.initStrategy(strategyClass, setting)
            self.runBacktesting()
            d = self.calculateBacktestingResult()
            try:
                targetValue = d[targetName]
            except KeyError:
                targetValue = 0
            resultList.append(([str(setting)], targetValue))

        # 显示结果
        resultList.sort(reverse=True, key=lambda result: result[1])
        self.output('-' * 30)
        self.output(u'优化结果：')
        for result in resultList:
            self.output(u'%s: %s' % (result[0], result[1]))
        return result

    #----------------------------------------------------------------------
    def runParallelOptimization(self, strategyClass, optimizationSetting):
        """并行优化参数"""
        # 获取优化设置
        settingList = optimizationSetting.generateSetting()
        targetName = optimizationSetting.optimizeTarget

        # 检查参数设置问题
        if not settingList or not targetName:
            self.output(u'优化设置有问题，请检查')

        # 多进程优化，启动一个对应CPU核心数量的进程池
        pool = multiprocessing.Pool(multiprocessing.cpu_count())
        l = []

        for setting in settingList:
            l.append(
                pool.apply_async(
                    optimize, (strategyClass, setting, targetName, self.mode,
                               self.startDate, self.initDays, self.endDate,
                               self.slippage, self.rate, self.size,
                               self.priceTick, self.dbName, self.symbol)))
        pool.close()
        pool.join()

        # 显示结果
        resultList = [res.get() for res in l]
        resultList.sort(reverse=True, key=lambda result: result[1])
        self.output('-' * 30)
        self.output(u'优化结果：')
        for result in resultList:
            self.output(u'%s: %s' % (result[0], result[1]))

    #----------------------------------------------------------------------
    def updateDailyClose(self, dt, price):
        """更新每日收盘价"""
        date = dt.date()

        if date not in self.dailyResultDict:
            self.dailyResultDict[date] = DailyResult(date, price)
        else:
            self.dailyResultDict[date].closePrice = price

    #----------------------------------------------------------------------
    def calculateDailyResult(self):
        """计算按日统计的交易结果"""
        self.output(u'计算按日统计结果')

        # 将成交添加到每日交易结果中
        for trade in self.tradeDict.values():
            date = trade.dt.date()
            dailyResult = self.dailyResultDict[date]
            dailyResult.addTrade(trade)

        # 加入清算交易
        for trade in self.liquidation.values():
            dailyResult.addTrade(trade)

        # 遍历计算每日结果
        previousClose = 0
        openPosition = 0
        for dailyResult in self.dailyResultDict.values():
            dailyResult.previousClose = previousClose
            previousClose = dailyResult.closePrice

            dailyResult.calculatePnl(openPosition, self.size, self.rate,
                                     self.slippage)
            openPosition = dailyResult.closePosition

        # 生成DataFrame
        resultDict = {k: [] for k in dailyResult.__dict__.keys()}
        for dailyResult in self.dailyResultDict.values():
            for k, v in dailyResult.__dict__.items():
                resultDict[k].append(v)

        resultDf = pd.DataFrame.from_dict(resultDict)

        # 计算衍生数据
        resultDf = resultDf.set_index('date')

        return resultDf

    #----------------------------------------------------------------------
    def calculateDailyStatistics(self, df):
        """计算按日统计的结果"""
        df['balance'] = df['netPnl'].cumsum() + self.capital
        df['return'] = (
            np.log(df['balance']) - np.log(df['balance'].shift(1))).fillna(0)
        df['highlevel'] = df['balance'].rolling(
            min_periods=1, window=len(df), center=False).max()
        df['drawdown'] = df['balance'] - df['highlevel']
        df['ddPercent'] = df['drawdown'] / df['highlevel'] * 100

        # 计算统计结果
        startDate = df.index[0]
        endDate = df.index[-1]

        totalDays = len(df)
        profitDays = len(df[df['netPnl'] > 0])
        lossDays = len(df[df['netPnl'] < 0])

        endBalance = df['balance'].iloc[-1]
        maxDrawdown = df['drawdown'].min()
        maxDdPercent = df['ddPercent'].min()

        totalNetPnl = df['netPnl'].sum()
        dailyNetPnl = totalNetPnl / totalDays

        totalCommission = df['commission'].sum()
        dailyCommission = totalCommission / totalDays

        totalSlippage = df['slippage'].sum()
        dailySlippage = totalSlippage / totalDays

        totalTurnover = df['turnover'].sum()
        dailyTurnover = totalTurnover / totalDays

        totalTradeCount = df['tradeCount'].sum()
        dailyTradeCount = totalTradeCount / totalDays

        totalReturn = (endBalance / self.capital - 1) * 100
        annualizedReturn = totalReturn / totalDays * 240
        dailyReturn = df['return'].mean() * 100
        returnStd = df['return'].std() * 100

        if returnStd:
            #二分利息
            sharpeRatio = (dailyReturn - 0.02 / 30) / returnStd * np.sqrt(240)
        else:
            sharpeRatio = 0

        # 返回结果
        result = {
            'startDate': startDate,
            'endDate': endDate,
            'totalDays': totalDays,
            'profitDays': profitDays,
            'lossDays': lossDays,
            'endBalance': endBalance,
            'maxDrawdown': maxDrawdown,
            'maxDdPercent': maxDdPercent,
            'totalNetPnl': totalNetPnl,
            'dailyNetPnl': dailyNetPnl,
            'totalCommission': totalCommission,
            'dailyCommission': dailyCommission,
            'totalSlippage': totalSlippage,
            'dailySlippage': dailySlippage,
            'totalTurnover': totalTurnover,
            'dailyTurnover': dailyTurnover,
            'totalTradeCount': totalTradeCount,
            'dailyTradeCount': dailyTradeCount,
            'totalReturn': totalReturn,
            'annualizedReturn': annualizedReturn,
            'dailyReturn': dailyReturn,
            'returnStd': returnStd,
            'sharpeRatio': sharpeRatio
        }

        return df, result

    #----------------------------------------------------------------------
    def showDailyResult(self, df=None, result=None):
        """显示按日统计的交易结果"""
        if df is None:
            df = self.calculateDailyResult()
            df, result = self.calculateDailyStatistics(df)

        # 输出统计结果
        self.output('-' * 50)
        # self.output(u'首个交易日：\t%s' % result['startDate'])
        # self.output(u'最后交易日：\t%s' % result['endDate'])

        # self.output(u'总交易日：\t%s' % result['totalDays'])
        # self.output(u'盈利交易日\t%s' % result['profitDays'])
        # self.output(u'亏损交易日：\t%s' % result['lossDays'])

        # self.output(u'起始资金：\t%s' % self.capital)
        # self.output(u'结束资金：\t%s' % formatNumber(result['endBalance']))

        # self.output(u'总收益率：\t%s%%' % formatNumber(result['totalReturn']))
        # self.output(u'年化收益：\t%s%%' % formatNumber(result['annualizedReturn']))
        # self.output(u'总盈亏：\t%s' % formatNumber(result['totalNetPnl']))
        # self.output(u'最大回撤: \t%s' % formatNumber(result['maxDrawdown']))
        # self.output(u'百分比最大回撤: %s%%' % formatNumber(result['maxDdPercent']))

        # self.output(u'总手续费：\t%s' % formatNumber(result['totalCommission']))
        # self.output(u'总滑点：\t%s' % formatNumber(result['totalSlippage']))
        # self.output(u'总成交金额：\t%s' % formatNumber(result['totalTurnover']))
        # self.output(u'总成交笔数：\t%s' % formatNumber(result['totalTradeCount']))

        # self.output(u'日均盈亏：\t%s' % formatNumber(result['dailyNetPnl']))
        # self.output(u'日均手续费：\t%s' % formatNumber(result['dailyCommission']))
        # self.output(u'日均滑点：\t%s' % formatNumber(result['dailySlippage']))
        # self.output(u'日均成交金额：\t%s' % formatNumber(result['dailyTurnover']))
        # self.output(u'日均成交笔数：\t%s' % formatNumber(result['dailyTradeCount']))

        # self.output(u'日均收益率：\t%s%%' % formatNumber(result['dailyReturn']))
        # self.output(u'收益标准差：\t%s%%' % formatNumber(result['returnStd']))
        # self.output(u'Sharpe Ratio：\t%s' % formatNumber(result['sharpeRatio']))

        try:
            # 显示结果信息
            import pandas as pd
            info = [
                [u'首个交易日：', result['startDate']],
                [u'最后交易日：', result['endDate']],
                [u'总交易日：', result['totalDays']],
                [u'盈利交易日', result['profitDays']],
                [u'亏损交易日：', result['lossDays']],
                [u'起始资金：', self.capital],
                [u'结束资金：', formatNumber(result['endBalance'])],
                [u'总收益率：', formatNumber(result['totalReturn'])],
                [u'年化收益：', formatNumber(result['annualizedReturn'])],
                [u'总盈亏：', formatNumber(result['totalNetPnl'])],
                [u'最大回撤: ', formatNumber(result['maxDrawdown'])],
                [u'百分比最大回撤: ',
                 formatNumber(result['maxDdPercent'])],
                [u'总手续费：', formatNumber(result['totalCommission'])],
                [u'总滑点：', formatNumber(result['totalSlippage'])],
                [u'总成交金额：', formatNumber(result['totalTurnover'])],
                [u'总成交笔数：', formatNumber(result['totalTradeCount'])],
                [u'日均盈亏：', formatNumber(result['dailyNetPnl'])],
                [u'日均手续费：', formatNumber(result['dailyCommission'])],
                [u'日均滑点：', formatNumber(result['dailySlippage'])],
                [u'日均成交金额：', formatNumber(result['dailyTurnover'])],
                [u'日均成交笔数：',
                 formatNumber(result['dailyTradeCount'])],
                [u'日均收益率：', formatNumber(result['dailyReturn'])],
                [u'收益标准差：', formatNumber(result['returnStd'])],
                [u'Sharpe Ratio：',
                 formatNumber(result['sharpeRatio'])],
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

        try:
            import matplotlib.pyplot as plt
            # 绘图
            fig = plt.figure(figsize=(10, 16 + 2))  # 1 for space
            plt.subplots_adjust(hspace=0.5)

            pBalance = plt.subplot(4, 1, 1)
            pBalance.set_title('Balance')
            df['balance'].plot(legend=True)

            pDrawdown = plt.subplot(4, 1, 2)
            pDrawdown.set_title('Drawdown')
            pDrawdown.fill_between(range(len(df)), df['drawdown'].values)

            pPnl = plt.subplot(4, 1, 3)
            pPnl.set_title('Daily Pnl')
            pPnl.bar(range(len(df['netPnl'])), df['netPnl'].values)

            # df['netPnl'].plot(kind='bar', legend=False, grid=False, xticks=[])
            # seqerator = max(1, result['totalDays'] // 7)
            # pPnl.set_xticks(pPnl.get_xticks()[::seqerator])

            pKDE = plt.subplot(4, 1, 4)
            pKDE.set_title('Daily Pnl Distribution')
            df['netPnl'].hist(bins=50)

            plt.show()
            plt.savefig('./temp/dailyResult.png')
            df['tradeList'] = None
            df.to_csv('./temp/dailyResult.csv')
            plt.close()

        except ImportError as identifier:
            pass
        except:
            print('-' * 20)
            print('Failed to plot daily curve')
            #traceback.print_exc()
            pass


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


########################################################################
class DailyResult(object):
    """每日交易的结果"""

    #----------------------------------------------------------------------
    def __init__(self, date, closePrice):
        """Constructor"""
        self.date = date  # 日期
        self.closePrice = closePrice  # 当日收盘价
        self.previousClose = 0  # 昨日收盘价

        self.tradeList = []  # 成交列表
        self.tradeCount = 0  # 成交数量

        self.openPosition = 0  # 开盘时的持仓
        self.closePosition = 0  # 收盘时的持仓

        self.tradingPnl = 0  # 交易盈亏
        self.positionPnl = 0  # 持仓盈亏
        self.totalPnl = 0  # 总盈亏

        self.turnover = 0  # 成交量
        self.commission = 0  # 手续费
        self.slippage = 0  # 滑点
        self.netPnl = 0  # 净盈亏

    #----------------------------------------------------------------------
    def addTrade(self, trade):
        """添加交易"""
        self.tradeList.append(trade)

    #----------------------------------------------------------------------
    def calculatePnl(self, openPosition=0, size=1, rate=0, slippage=0):
        """
        计算盈亏
        size: 合约乘数
        rate：手续费率
        slippage：滑点点数
        """
        # 持仓部分
        self.openPosition = openPosition
        self.positionPnl = self.openPosition * (
            self.closePrice - self.previousClose) * size
        self.closePosition = self.openPosition

        # 交易部分
        self.tradeCount = len(self.tradeList)

        for trade in self.tradeList:
            if trade.direction == DIRECTION_LONG:
                posChange = trade.volume
            else:
                posChange = -trade.volume

            self.tradingPnl += posChange * (
                self.closePrice - trade.price) * size
            self.closePosition += posChange
            self.turnover += trade.price * trade.volume * size
            self.commission += trade.price * trade.volume * size * rate
            self.slippage += trade.volume * size * slippage

        # 汇总
        self.totalPnl = self.tradingPnl + self.positionPnl
        self.netPnl = self.totalPnl - self.commission - self.slippage


########################################################################
class OptimizationSetting(object):
    """优化设置"""

    #----------------------------------------------------------------------
    def __init__(self):
        """Constructor"""
        self.paramDict = OrderedDict()

        self.optimizeTarget = ''  # 优化目标字段

    #----------------------------------------------------------------------
    def addParameter(self, name, start, end=None, step=None):
        """增加优化参数"""
        if end is None and step is None:
            self.paramDict[name] = [start]
            return

        if end < start:
            print(u'参数起始点必须不大于终止点')
            return

        if step <= 0:
            print(u'参数布进必须大于0')
            return

        l = []
        param = start

        while param <= end:
            l.append(param)
            param += step

        self.paramDict[name] = l

    #----------------------------------------------------------------------
    def generateSetting(self):
        """生成优化参数组合"""
        # 参数名的列表
        nameList = self.paramDict.keys()
        paramList = self.paramDict.values()

        # 使用迭代工具生产参数对组合
        productList = list(product(*paramList))

        # 把参数对组合打包到一个个字典组成的列表中
        settingList = []
        for p in productList:
            d = dict(zip(nameList, p))
            settingList.append(d)

        return settingList

    #----------------------------------------------------------------------
    def setOptimizeTarget(self, target):
        """设置优化目标字段"""
        self.optimizeTarget = target


#----------------------------------------------------------------------
def formatNumber(n):
    """格式化数字到字符串"""
    rn = round(n, 2)  # 保留两位小数
    return format(rn, ',')  # 加上千分符


#----------------------------------------------------------------------
def optimize(strategyClass, setting, targetName, mode, startDate, initDays,
             endDate, slippage, rate, size, priceTick, dbName, symbol):
    """多进程优化时跑在每个进程中运行的函数"""
    engine = BacktestingEngine()
    engine.setBacktestingMode(mode)
    engine.setStartDate(startDate, initDays)
    engine.setEndDate(endDate)
    engine.setSlippage(slippage)
    engine.setRate(rate)
    engine.setSize(size)
    engine.setPriceTick(priceTick)
    engine.setDatabase(dbName, symbol)

    engine.initStrategy(strategyClass, setting)
    engine.runBacktesting()

    #df = engine.calculateDailyResult()
    #df, d = engine.calculateDailyStatistics(df)
    d = engine.calculateBacktestingResult()
    try:
        targetValue = d[targetName]
    except KeyError:
        targetValue = 0
    return (str(setting), targetValue)
