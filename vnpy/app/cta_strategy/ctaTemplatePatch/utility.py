# encoding: UTF-8

'''
本文件包含了CTA引擎中的策略开发用模板。
添加了一些基本的策略属性，变量。不做下单逻辑
'''
from vnpy.app.cta_strategy.base import EngineType
from datetime import MINYEAR
import logging
import numpy as np

from datetime import datetime,time,date,timedelta
import json,time
class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)

#--------------------------------------------------------------------------
def tradeDictToJSON(trade):
    """交易信息格式化"""
    return json.dumps(trade.__dict__,cls=DateTimeEncoder,indent=4,ensure_ascii=False)

def isclose(a, b, ndigits = 10):
       return round(a-b, ndigits) == 0

#########################################################################
def timeit(method):
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
    
# def defaultCache(func):
    
#     from vnpy.trader.app.ctaStrategy.caching import Cache
#     func1 = Cache(ttl=60*60,maxsize=1024*1024*128)(func)
#     func2 = Cache(ttl=60*60*24,maxsize=1024*1024*128, filepath='./temp/' + func.__name__)(func)

#     #@timeit
#     def decorator(self, *args, **kwargs):
#         if self.ctaEngine.engineType == ENGINETYPE_TRADING:
#             return func1(self,*args, **kwargs)
#         else:
#             return func2(self,*args, **kwargs)

#     return decorator

#---------------------------------------------------------------
def diffVolume(volumeArray):
    #return volumeArray
    """
    将跨交易日的累积成交量做Diff运算
    """
    volume = np.diff(volumeArray)
    #volume = np.where(volume<0,0,volume)
    volume[volume < 1 ]= 1 # 

    #buf-fix: 使用连续成交量进行计算，考虑中间新交易日间断的情况
    #更新最后一个差值
    if volume[-1] < 0:
        volume[-1] = volumeArray[-1]
    mask = volume<0  #小于0的是跨交易日第一个BAR的成交量

    #使用交易日第一个BAR的成交量代替
    mask_ori = mask.copy()
    mask_ori[1:] = mask[:-1]
    mask_ori[0] = False
    # -2 ,diff操作后arraySize会减少1
    volume[mask] = volumeArray[:-1][mask_ori]

    return volume