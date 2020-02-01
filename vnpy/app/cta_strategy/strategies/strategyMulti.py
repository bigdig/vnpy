# encoding: UTF-8

"""
多策略组合回策：依据CTA_setting配置的策略、手数进行组合回测

"""

from vnpy.app.cta_strategy.ctaTemplatePatch import CtaTemplatePatch
from vnpy.app.cta_strategy.strategies import STRATEGY_CLASS
# from vnpy.app.cta_strategy.ctaBacktestingDecorator import backtesting
from vnpy.trader.constant import Direction, Status, Offset, Interval
from vnpy.app.cta_strategy.base import EngineType
import json
import os
import copy
from vnpy.trader.vtFunction import getJsonPath


"""Support for simple JSON templates.
A JSON template is a dictionary of JSON data in which string values
may be simple templates in string.Template format (i.e.,
$dollarSignEscaping).  By default, the template is expanded against
its own data, optionally updated with additional context.
"""

import json
from string import Template
import sys

__author__ = 'smulloni@google.com (Jacob Smullyan)'


def ExpandJsonTemplate(json_data, extra_context=None, use_self=True):
    """Recursively template-expand a json dict against itself or other context.
    The context for string expansion is the json dict itself by default, updated
    by extra_context, if supplied.
    Args:
    json_data: (dict) A JSON object where string values may be templates.
    extra_context: (dict) Additional context for template expansion.
    use_self: (bool) Whether to expand the template against itself, or only use
        extra_context.
    Returns:
    A dict where string template values have been expanded against
    the context.
    """
    if use_self:
        context = dict(json_data)
    else:
        context = {}
    if extra_context:
        context.update(extra_context)

    def RecursiveExpand(obj):
        if isinstance(obj, list):
            return [RecursiveExpand(x) for x in obj]
        elif isinstance(obj, dict):
            return dict((k, RecursiveExpand(v)) for k, v in obj.items())
        elif isinstance(obj, (str, type(u''))):
            return Template(obj).substitute(context)
        else:
            return obj

    return RecursiveExpand(json_data)
  
########################################################################
# @backtesting
class MultiStrategy(CtaTemplatePatch):
    """多策略合并策略，负责将多个配置文件中的策略加载到CTAEngine中"""
    className = 'MultiStrategy'
    author = u'renxg'

    settingFile = None                        #string or list
    parameters = CtaTemplatePatch.parameters + \
                ['settingFile','exitOnTopRtnPips','halfTime','isVirtual']

    sortedStrategyItems = []

    # 参数调优
    exitOnTopRtnPips = 0.008
    halfTime = 60
    posMultiper = 1
    isVirtual = True

    #----------------------------------------------------------------------
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        if isinstance(self.settingFile,list):
            settingFile = self.settingFile
            self.settingFile = '' #不能显示
            for st in settingFile:
                self.loadSettingFile(st)
        else:
            self.loadSettingFile(self.settingFile)

    #----------------------------------------------------------------------
    def loadSettingFile(self, settingFile):
        """加载配置"""
        settingFilePath = getJsonPath(settingFile,__file__)  
        with open(settingFilePath) as f:
            l = json.load(f)
            
            for setting in l:
                #json expand, 设置vt_symbol posMultiper
                extra = dict(
                    strategy_name = self.strategy_name,
                    vt_symbol=self.vt_symbol,
                    posMultiper=self.posMultiper,
                    kLineCycle=self.kLineCycle,
                    exitOnTopRtnPips = self.exitOnTopRtnPips,
                    isVirtual = self.isVirtual,
                    halfTime = self.halfTime)

                setting = ExpandJsonTemplate(setting,extra)
                print(setting)

                if self.get_engine_type() == EngineType.LIVE and setting["className"] != self.className:
                    # 处理实盘非组合策略
                    self.cta_engine.loadStrategy(setting)
                else:
                    self.loadStrategy(setting)
                    #排序，与实盘一致
                    self.sortedStrategyItems = sorted(self.cta_engine.strategyDict.items(), key = lambda item:item[0],reverse = True)

    #----------------------------------------------------------------------
    # @timeit
    def on_init(self):
        """初始化策略（必须由用户继承实现）"""

        if self.get_engine_type() == EngineType.LIVE:
            return

        self.write_log(u'策略实例统计数量：%s' % len(self.sortedStrategyItems)) 
        for name, s in self.sortedStrategyItems:
            s.inited = True
            s.on_init()

        self.put_event()

    #----------------------------------------------------------------------
    def on_start(self):
        """启动策略（必须由用户继承实现）"""
        super(MultiStrategy, self).on_start()

        if self.get_engine_type() == EngineType.LIVE:
            return

        print(self.sortedStrategyItems)
        for name, s in self.sortedStrategyItems:
            s.trading = True
            s.on_start()
        self.put_event()

    #----------------------------------------------------------------------
    def on_stop(self):
        """停止策略（必须由用户继承实现）"""
        super(MultiStrategy, self).on_stop()

        if self.get_engine_type() == EngineType.LIVE:
            return

        for name, s in self.sortedStrategyItems:
            s.trading = False
            s.on_stop()
        self.put_event()
        
    #----------------------------------------------------------------------
    def on_tick(self, tick):
        """收到行情TICK推送（必须由用户继承实现）"""
        #无效（会回调onBar)
        #super(MultiStrategy, self).onTick(tick)
        if self.get_engine_type() == EngineType.LIVE:
            return

        for name, s in self.sortedStrategyItems:
            if s.vt_symbol == tick.vt_symbol:
                s.on_tick(tick)
        pass
        

    #----------------------------------------------------------------------
    def on_bar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        #无效
        #super(MultiStrategy, self).onBar(bar)
        if self.get_engine_type() == EngineType.LIVE:
            return
            
        for name, s in self.sortedStrategyItems:
            if s.vt_symbol == bar.vt_symbol:
                s.on_bar(bar)
        pass

    #----------------------------------------------------------------------
    def loadStrategy(self,setting):
        """载入策略"""
        try:
            strategy_name = setting['strategy_name']
            className = setting['className']
            enable = setting['enable']
            if not enable:
                self.write_log(u'策略类：%s not enabled' %className)
                return
        except Exception as e:
            print(u'载入策略出错：%s' %e)
            return
        
        # 获取策略类
        strategyClass = STRATEGY_CLASS.get(className, None)
        if not strategyClass:
            self.write_log(u'找不到策略类：%s' %className)
            return
        
        # 防止策略重名
        if strategy_name in self.cta_engine.strategyDict:
            self.write_log(u'策略实例重名：%s' %strategy_name)
        else:
            # 创建策略实例
            strategy = strategyClass(self.cta_engine, strategy_name, self.vt_symbol, setting)
            # 将其它策略放个Engine 
            if not strategy.className  == self.className:
                #同步到ctaEngine中
                self.cta_engine.strategyDict[strategy_name] = strategy
