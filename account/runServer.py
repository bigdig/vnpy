
# encoding: UTF-8

import sys
if sys.version_info < (3, 0):
    reload(sys)
    sys.setdefaultencoding('utf8')

sys.path.append('../')
sys.path.append('../../')
sys.path.append('../../vnpy/trader/')

import multiprocessing
import signal
from time import sleep
from datetime import datetime, time


import vnpy.trader.vtPath
from vnpy.event.eventType import *
from vnpy.trader.vtEngine import MainEngine,LogEngine
from vnpy.event.eventEngine import Event
from vnpy.trader.vtEvent import *
from vnpy.trader.vtFunction import isRecordingTime, isTradingTime

# 加载底层接口
try:
    from vnpy.trader.gateway import ctpGateway  
except ImportError:
    print("ctpGateway load failed!")
    pass

# 加载上层应用
from vnpy.trader.app import (riskManager,dataRecorder,rpcService,ctaStrategy,spreadTrading,algoTrading)

def isRestartTime():
    currentTime = datetime.now().time()
    currentTime = int(currentTime.strftime("%H%M"))
    restart = False
    # 判断当前处于的时间段
    if (currentTime == 850 or
        currentTime == 2050):
        restart = True

    return restart

#----------------------------------------------------------------------
def processErrorEvent(event):
    """
    处理错误事件
    错误信息在每次登陆后，会将当日所有已产生的均推送一遍，所以不适合写入日志
    """
    error = event.dict_['data']
    print(u'错误代码：%s，错误信息：%s' %(error.errorID, error.errorMsg))

 #----------------------------------------------------------------------
def runChildProcess():
    """子进程运行函数"""
    # print '-'*20

    # 创建日志引擎
    le = LogEngine()
    le.setLogLevel(le.LEVEL_INFO)
    le.addConsoleHandler()
    le.addFileHandler()
    le.info(u'启动行情记录运行子进程')

    # 创建主引擎
    me = MainEngine()

    ee = me.eventEngine
    ee.register(EVENT_LOG, le.processLogEvent)
    ee.register(EVENT_CTA_LOG, le.processLogEvent)
    ee.register(EVENT_ERROR, processErrorEvent)

    try:
        # 添加交易接口
        try:
            me.addGateway(ctpGateway) 
        except:
            pass
        
        # 添加上层应用
        me.addApp(riskManager)
        me.addApp(dataRecorder)
        #fix: 当服务端初始化完毕后再开启rpcService
        #me.addApp(rpcService)
        me.addApp(ctaStrategy)
        me.addApp(spreadTrading)
        me.addApp(algoTrading)
        
        le.info(u'主引擎创建成功')

        # 自动建立MongoDB数据库
        me.dbConnect()
        le.info(u'connect MongoDB')

        # 自动建立CTP链接
        me.connect('CTP')
        le.info(u'连接CTP接口')

        # 取仓位信息
        me.qryPosition("CTP")

        while not me.getAllContracts():
            sleep(5)
            le.info(u'收集合约信息...')

        sleep(3)
        le.info(u'合约信息中数量: %s' % len(me.getAllContracts()))
        # 及时保存数据引擎里的合约数据到硬盘
        me.dataEngine.saveContracts()

        #服务端初始化完成

        #开启RPC
        me.addApp(rpcService)
        le.info(u'开启RPCService')

        '''
        bug-fix: 休息，以便于客户端连接上来收CTP信息
        '''
        sleep(5.)

        #CTP连接完成，发送重启信号
        event = Event(EVENT_CTP_RESTARTED)
        me.eventEngine.put(event)
        le.info(u'通知客户端CTP RESTART')

        while True:
            sleep(1)
    except KeyboardInterrupt:
        le.info(u"Keyboard interrupt in process")
    finally:
        le.info(u"cleaning up")

        #exit 有时会一直无法退出，暂且屏了
        # try:
        #     me.exit()
        # except Exception as e:
        #     self.writeLog(u'Engine退出出错：%s' %e)

#----------------------------------------------------------------------
# @Daemon('TradeServer.pid')
def runParentProcess():
    """父进程运行函数"""
    # 创建日志引擎
    print(u'启动行情记录守护父进程')
        
    p = None        # 子进程句柄

    while True:
        # 记录时间则需要启动子进程
        if p is None:
            print(u'启动子进程')
            p = multiprocessing.Process(target=runChildProcess)
            p.daemon = True
            p.start()
            print(u'子进程启动成功')
            sleep(60) #一分钟时间窗口(避免再次重启)

        # 开盘时重启子进程(先关闭，然后循环后会重启)
        if p is not None and isRestartTime() :
            print(u'关闭子进程')
            p.terminate()
            p.join()
            p = None
            print(u'子进程关闭成功')

        sleep(7)

if __name__ == '__main__':
    runParentProcess()