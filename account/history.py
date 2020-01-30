# encoding: utf-8
import sys
sys.path.append('../')
sys.path.append('../../')
sys.path.append('../../vnpy/trader/')

from vnpy.trader.app.ctaStrategy.ctaHistoryData import HistoryDataEngine

"""
##需要更新dates.json API key 
1. dc9b4572b2f2c3fdb69342ed3d29a924a37f7f602878cd42be7aac1d29a1a945
2. https://mall.datayes.com/apidemo/1296?lang=zh
"""
if __name__ == '__main__':
    from time import sleep
    e = HistoryDataEngine()
    sleep(1)
    e.downloadFuturesIntradayBar('rb1801')