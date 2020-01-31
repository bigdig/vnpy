# encoding: UTF-8

"""
通过VT_setting.json加载全局配置
"""

import os
import traceback
import json
from vnpy.trader.vtFunction import getJsonPath


settingFileName = "VT_setting.json"
settingFilePath = getJsonPath(settingFileName, __file__)

globalSetting = {}      # 全局配置字典

try:
    with open(settingFilePath) as f:
        setting = f.read()
        if type(setting) is not str:
            setting = str(setting, encoding='utf8')
        globalSetting = json.loads(setting)

        #检测可用性，起用mongoHost1
        from pymongo.errors import ConnectionFailure
        import pymongo
        try:
            uri = 'mongodb://root:password@' + globalSetting['mongoHost'] + ':' + str(globalSetting['mongoPort']) + '/?serverSelectionTimeoutMS=200'
            client = pymongo.MongoClient(uri, connect=False)
            client.admin.command('ismaster')

            globalSetting["mongoHost"] = 'mongodb://root:password@' + globalSetting['mongoHost']
        except ConnectionFailure:
            globalSetting['mongoHost'] = 'mongodb://root:password@' + globalSetting['mongoHost1']
            print("Default Mongo server not available, use backup Server ")
            

except:
    traceback.print_exc()