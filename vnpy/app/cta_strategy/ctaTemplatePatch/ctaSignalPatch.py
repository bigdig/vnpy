# encoding: UTF-8

'''
CtaSignalPatch
对信号计算进行延迟操作，提高信号加载速度
'''

from vnpy.app.cta_strategy import CtaSignal

########################################################################
class CtaSignalPatch(CtaSignal):
    """CtaSignalPatch"""

    # 参数
    trading = False
    strategy = None

    #----------------------------------------------------------------------
    def __init__(self, strategy=None):
        """Constructor"""
        super(CtaSignalPatch, self).__init__()
        self.strategy = strategy

    #----------------------------------------------------------------------
    def get_signal_pos(self):
        """取信号"""
        #取信号方法，则激活
        if not self.trading:
            self.trading = True
            self.updateSignal()

        return super(CtaSignalPatch,self).get_signal_pos()

    #----------------------------------------------------------------------
    def updateSignal(self):
        """更新信号（必须由用户继承实现）"""
        raise NotImplementedError

    #----------------------------------------------------------------------
    def writeCtaLog(self, content):
        """记录CTA日志"""
        if self.strategy:
             self.strategy.writeCtaLog(content)
