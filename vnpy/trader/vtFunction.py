# encoding: UTF-8

"""
包含一些开发中常用的函数
"""
import os
import decimal
import json
import datetime as dt
import time
from datetime import datetime,time
import threading
import multiprocessing.pool
import functools
from math import isnan

MAX_NUMBER = 10000000000000
MAX_DECIMAL = 4

#----------------------------------------------------------------------
def safeUnicode(value):
    """检查接口数据潜在的错误，保证转化为的字符串正确"""
    # 检查是数字接近0时会出现的浮点数上限
    if type(value) is int or type(value) is float:
        if value > MAX_NUMBER or isnan(value):
            value = 0

    # 检查防止小数点位过多
    if type(value) is float:
        d = decimal.Decimal(str(value))
        if abs(d.as_tuple().exponent) > MAX_DECIMAL:
            value = round(value, ndigits=MAX_DECIMAL)

    return unicode(value)


# 图标路径
iconPathDict = {}

path = os.path.abspath(os.path.dirname(__file__))
for root, subdirs, files in os.walk(path):
    for fileName in files:
        if '.ico' in fileName:
            iconPathDict[fileName] = os.path.join(root, fileName)

#----------------------------------------------------------------------
def loadIconPath(iconName):
    """加载程序图标路径"""   
    global iconPathDict
    return iconPathDict.get(iconName, '')    
    

#----------------------------------------------------------------------
def getTempPath(name):
    """获取存放临时文件的路径"""
    tempPath = os.path.join(os.getcwd(), 'temp')
    if not os.path.exists(tempPath):
        os.makedirs(tempPath)
        
    path = os.path.join(tempPath, name)
    return path


# JSON配置文件路径
jsonPathDict = {}

#----------------------------------------------------------------------
def getJsonPath(name, moduleFile):
    """
    获取JSON配置文件的路径：
    1. 优先从当前工作目录查找JSON文件
    2. 若无法找到则前往模块所在目录查找
    """
    currentFolder = os.getcwd()
    currentJsonPath = os.path.join(currentFolder, name)
    if os.path.isfile(currentJsonPath):
        jsonPathDict[name] = currentJsonPath
        return currentJsonPath
    
    moduleFolder = os.path.abspath(os.path.dirname(moduleFile))
    moduleJsonPath = os.path.join(moduleFolder, '.', name)
    jsonPathDict[name] = moduleJsonPath
    return moduleJsonPath

vtGlobalSetting = None
#----------------------------------------------------------------------
def loadMongoSetting():
    """载入MongoDB数据库的配置"""

    global vtGlobalSetting
    setting = vtGlobalSetting

    if setting == None:
        """载入MongoDB数据库的配置"""
        fileName = 'VT_setting.json'
        filePath = getJsonPath(fileName,__file__)
        f = open(filePath)
        setting = json.load(f)

        #检测可用性，起用mongoHost1
        from pymongo.errors import ConnectionFailure
        import pymongo
        try:
            uri = 'mongodb://root:password@' + setting['mongoHost'] + ':' + str(setting['mongoPort']) + '/?serverSelectionTimeoutMS=200'
            client = pymongo.MongoClient(uri, connect=False)
            client.admin.command('ismaster')
        except ConnectionFailure:
            setting['mongoHost'] = setting['mongoHost1']
            print("Default Mongo server not available, use backup Server ")
        
        vtGlobalSetting = setting


    host = 'mongodb://root:password@' + setting['mongoHost']
    port = setting['mongoPort']
    logging = setting['mongoLogging']    

    return host, port, logging

#----------------------------------------------------------------------
def todayDate():
    """获取当前本机电脑时间的日期"""
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


# from vnpy.trader.timeout_decorate import timeout
# def setInterval(interval):
#     def decorator(function):
#         def wrapper(*args, **kwargs):
#             stopped = threading.Event()

#             def loop(): # executed in another thread
#                 while not stopped.wait(interval): # until stopped
#                     #function(*args, **kwargs)
#                     try:
#                         timeout(interval,False)(function)(*args,**kwargs)
#                     except :
#                         pass
#                     else:
#                         pass

#             t = threading.Thread(target=loop)
#             t.daemon = True # stop if the program exits
#             t.start()
#             return stopped
#         return wrapper
#     return decorator

class RemoteSetting(object):
    """RPC服务引擎"""
    
    settingFileName = 'RS_setting.json'
    settingFilePath = getJsonPath(settingFileName, __file__)    
    
    name = u'RPC服务'

    #----------------------------------------------------------------------
    def __init__(self):
        """Constructor"""
        host,port,log = loadMongoSetting()
        self.host = host[host.find('@')+1:]
        if not self.host:
            self.host = host

        self.loadSetting()
        
    #----------------------------------------------------------------------
    def loadSetting(self):
        """读取配置"""
        with open(self.settingFilePath) as f:
            d = json.load(f)
            
            self.repAddress = d['repAddress'].replace('*',self.host)
            self.pubAddress = d['pubAddress'].replace('*',self.host)


#-------------------------------------------------------------------------------------------------------
#国内正规期货市场交易时间为周一至周五早上9点到11点半，下午1点半到15点结束。 早上10：15到10：30休息15分钟，夜盘：21点到日凌晨2:30分。
def isRecordingTime(dt, DAY_START = time(8, 30),DAY_END = time(15, 18),NIGHT_START = time(20, 30),NIGHT_END = time(2, 33)):
    currentTime = dt.time()
    recording = False

    # 判断当前处于的时间段
    if ((currentTime >= DAY_START and currentTime <= DAY_END) or
        (currentTime >= NIGHT_START) or
        (currentTime <= NIGHT_END)):
        recording = True
        
    # 过滤周末时间段
    weekday = dt.isoweekday()
    if ((weekday == 6 and currentTime > NIGHT_END)  or weekday == 7):
        recording = False

    return recording

#-------------------------------------------------------------------------------------------------------
def isNotTradingTime(time,timeRanges=[
    (datetime.strptime("02:30:00", "%H:%M:%S").time(), datetime.strptime("08:59:59", "%H:%M:%S").time()), #night rest
    (datetime.strptime("10:15:00", "%H:%M:%S").time(), datetime.strptime("10:29:59", "%H:%M:%S").time()), #morning rest
    (datetime.strptime("11:30:00", "%H:%M:%S").time(), datetime.strptime("13:29:59", "%H:%M:%S").time()), #day rest
    (datetime.strptime("15:00:00", "%H:%M:%S").time(), datetime.strptime("20:59:59", "%H:%M:%S").time()), #afternoon rest
        ]):

    for tr in timeRanges:
        if tr[0] <= time <= tr[1]:
            return True
    return False
    pass

def isTradingTime(time):
    return not isNotTradingTime(time)
    pass 

# def isTradingTime(time,timeRanges=[
#     (datetime.strptime("09:00:00", "%H:%M:%S").time(), datetime.strptime("10:15:00", "%H:%M:%S").time()),
#     (datetime.strptime("10:30:00", "%H:%M:%S").time(), datetime.strptime("11:30:00", "%H:%M:%S").time()),
#     (datetime.strptime("13:30:00", "%H:%M:%S").time(), datetime.strptime("15:00:00", "%H:%M:%S").time()),
#     (datetime.strptime("21:00:00", "%H:%M:%S").time(), datetime.strptime("23:00:00", "%H:%M:%S").time())
#     ]):

#     for tr in timeRanges:
#         # [)
#         if tr[0] <= time < tr[1]:
#             return True
#     return False
#     pass 

#########################################################################
def timeit(method):
    import time
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()
        if 'log_time' in kw:
            name = kw.get('log_name', method.__name__.upper())
            kw['log_time'][name] = int((te - ts) * 1000)
        else:
            print ('%r  %2.2f ms' % \
                  (method.__name__, (te - ts) * 1000))
        return result
    return timed