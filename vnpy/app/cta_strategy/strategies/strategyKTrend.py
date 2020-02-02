from vnpy.app.cta_strategy import(
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager
)
from vnpy.trader.constant import Interval

import math
import sys
import datetime,time

from vnpy.app.cta_strategy.ctaTemplatePatch import CtaTemplatePatch

class KTrendStrategy(CtaTemplatePatch):
    '''
    简单快速趋势策略:
       开仓策略：采取模拟概率积分的方式，即 " 中长趋势线 + 短期趋势线 + 短期的日涨跌幅比例 + 日内分时高低差值" 组成
            a. 中长线趋 long_trend_ma(>=5d): 可以选择多条，采取“与“的方式，即所有选择线的趋势都是一致的，才认为趋势确定。
            b. 短期趋势 short_trend_ma(<=3d): 同中长线，可以选择多条，采取”与“的方式来确定。
            c. 短期涨跌幅比例(short_rate)：只有当短期内涨跌幅超过一个比例，才认为短期确定，采用累加的方式，或最大值的方式。
            d. 概率积分：针对前面3个条件，可以进行概率假设取值，并进行累加出总的假设概率(<1.0)，
               即 long_trend_ma *K_lt + short_trend_ma*K_st + short_rate*K_sr 。
            e. 日内分时高低差值(gap_rate)： 当时开仓时，也不要追高/追低，要根据日内分时的最高值或最低值一定的差值才进行开仓。
            f. 开仓的数量以1手为限定
        止损策略：采取偏离开仓价格限额的方式或最大损失值的原则，即设定一定的限额，在开仓时都必须同时设置
            a. 设定固定的平仓的价格损失比例
            b. 转换为对应的价格，再加一定的滑点值，以促进及时成交;
        止赢策略：当赢利超过一定比例或固定价格偏离值时，即触发止赢策略，具体操作可复用止损策略。
        风控策略: 针对如下的风险要进行风险控制
            a. 针对行情巨大的波动，如果损失已经超过了限额，但没能成交，要能动态调整设定的价格，以便保证成交;
            b. 发送给交易所委托，跨立易日后，这些数据可能被清除，需要开盘时重新发起委托。
    '''
    # 策略作者
    author = "kolaman@139.com"
    # 定义参数
    order_duo_kong = "D&K" # 交易哪个方向向，D:只开多仓，K: 只开空仓，D&K:都可以开
    bar_data_minutes = 60  # 控制生成BAR DATA的分钟数
    long_trend_ma_num = 8 # 长线趋势线分别为5d, 10d, 20d, 40d, 80d,...., 为2表示选择5d,10d
    short_trend_ma_num = 8 # 短期趋势线别为2d, 3d. 为2表示选择1d, 2d.
    short_rate = 0.01     # 表示价格要涨跌幅要3%以上
    k_lt = 0.4     # 表示长线趋势在总的假设概率中占比为40%
    k_st = 0.4     # 表示短线趋势在总的假设概率中占比为40% 
    K_sr = 0.2     # 表示短线波动幅度在总的假设概率中占比为20% 
    duo_kong_probability_threshold = 0.55   # 表示只有总的概超过此值后方可进行开仓
    kai_probability_threshold = 0.7   # 表示只有总的概超过此值后方可进行开仓
    kai_ping_price_allowance = 10 # 为了即时达成交易，相对于在当前价的基础进行对应加减，以快速的进行成交
    
    gap_rate = 0.005 # 表示日内的开仓价格需要与日内最高或日内最低偏离1%

    ping_cang_rate = 0.01 # 移动止赢止损平仓的波动控制在+/-%左右
    kai_num_per_order = 1 # 每次交易的开平手数

    # 定义变量
    # 支持中长线趋势的移动均线
    # 支持短线趋势的移动均线

    # 当前交易日的最高、最低价格, 用于配合gap_rate的判断
    cur_day_hour = -1  # 当前交易日的小时数，用于在没有tick数据的判断当前的交易日
    cur_day_high_price = 0.0 # 当前交易日的最高价格
    cur_day_low_price = sys.float_info.max # 当前交易日的最低价格
    trade_price = 0.0 # 持仓止赢的移动价格

    # 添加参数和变量名到对应的列表
    parameters = ["order_duo_kong", "bar_data_minutes", "long_trend_ma_num","short_trend_ma_num", 
        "short_rate", "k_lt", "k_st", "K_sr","duo_kong_probability_threshold","kai_probability_threshold",
        "kai_ping_price_allowance", "gap_rate","kai_num_per_order","ping_cang_rate"]
    variables = ["trade_price", "cur_day_high_price","cur_day_low_price","cur_day_hour"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        '''
        '''
        super(KTrendStrategy, self).__init__(
            cta_engine,strategy_name,vt_symbol,setting
            )
        # K线合成器：从Tick合成分钟K线用
        self.bg = BarGenerator(self.on_bar, self.bar_data_minutes, self.on_window_bar, Interval.MINUTE)
        # 时间序列容器：计算技术指标用
        self.am = ArrayManager()


    def on_bar(self, bar:BarData):
        '''
        通过该函数收到新的1分钟K线推送
        '''     
        #
        super().on_bar(bar)
        
        self.bg.update_bar(bar)

        #晚上8点夜盘前当前天，从夜盘开始算新的一天
        if((self.cur_day_hour == -1) or 
            ((self.cur_day_hour >8 and self.cur_day_hour <20)  and bar.datetime.hour>20)):
            self.cur_day_high_price = 0.0
            self.cur_day_low_price = sys.float_info.max
        #获取当前交易日的最高价和最低价
        self.cur_day_hour = bar.datetime.hour
        self.cur_day_high_price = max(self.cur_day_high_price,bar.high_price)
        self.cur_day_low_price = min(self.cur_day_low_price,bar.low_price)

        #
        # if(self.pos != 0):
        #     # 平仓分析
        #     self.ping_cang_analyse_bar(bar)
        # Write Log
        if(datetime.datetime.now().minute % 5 == 0):
            now = time.strftime('%Y-%m-%d %H:%M:%S')
            msg = now + " 收到1分钟K线推送"
            self.write_log(msg)
            msg = "持仓数:" + str(self.pos)+ " cur_day_hour:" + str(self.cur_day_hour) +" high price:" + str(self.cur_day_high_price) + " low price:" + str(self.cur_day_low_price)
            self.write_log(msg)
        
        # 同步变量到硬盘 sync_data data
        self.sync_data()
        self.put_event()

    def on_window_bar(self, bar:BarData):
        '''
        收到指定的WINDOW BAR数据
        '''
        self.write_log("收到指定Windows的BARDATA数据")
        #print(str(sys._getframe().f_lineno)+" on_bar_1d:")

        # 清空未成交委托：为了防止之前下的单子在上一个Window Bar没有成交，但是下一个Window Bar可能已经调整了价格，
        # 保证策略在当前这Window Bar开始时的整个状态是清晰和唯一的。
        self.cancel_all()

        am = self.am        

        # 更新K线到时间序列容器中   
        am.update_bar(bar)

        # 若缓存的K线数量尚不够计算技术指标，则直接返回
        if not am.inited:
            return

        if(self.pos == 0):
            # 开仓分析        
            self.kai_cang_analyse(bar)
        #else:
            # 平仓分析
        #    self.ping_cang_analyse(bar)


        # 更新    
        self.put_event()

        pass

    def trend_maker(self, ma_list):
        '''
        复用此函数来判断一组均线的走势, 头：DUO, 空：KONG, 非头空：NULL.
        '''
        trend_list = [] # 保存趋势判断，‘DUO’: 多头，'KONG': 空头, "NULL" : 非多非空

        for cur_lt in ma_list:
            #
            cur_lt_trend = []            
            for i in range(len(cur_lt)-1):
                if (not math.isnan(cur_lt[i])) and (not math.isnan(cur_lt[i+1])):
                    if(cur_lt[i+1] > cur_lt[i]):
                        cur_lt_trend.append("DUO")
                    elif (cur_lt[i+1] < cur_lt[i]):
                        cur_lt_trend.append("KONG")
                    else:
                        cur_lt_trend.append("NULL")

            duo_count = cur_lt_trend.count("DUO")          
            kong_count = cur_lt_trend.count("KONG")
            null_count = cur_lt_trend.count("NULL")
            sub_count = duo_count + kong_count + null_count
            #print("[trend_maker]]cur_lt count - DUO: ", duo_count, "KONG: ", kong_count, "NULL: ", null_count)
            if((duo_count)/sub_count > self.duo_kong_probability_threshold): # 多头方向的值大于一定的比例, 可认为是多头
                trend_list.append('DUO')
            elif ((kong_count)/sub_count > self.duo_kong_probability_threshold):# 空头方向的值大于一定的比例, 可认为是空头
                trend_list.append('KONG')
            else:
                trend_list.append('NULL') # 否则认为是振荡

        
        return trend_list

    def kai_cang_order(self, buy_or_short, price):
        '''
        开仓操作，买多或卖空        
        '''
        if( buy_or_short): # 开多仓
            self.write_log(" 开多仓")
            self.buy(price, self.kai_num_per_order)
            #print("[Kai Cang] Duo...")
        else:  # 开空仓
            self.write_log(" 开空仓")
            self.short(price, self.kai_num_per_order)
            #print("[Kai Cang] Kong...")
    
    def kai_cang_analyse(self, bar:BarData):
        '''
        是否开仓的策略分析, 整个策略的主要行为
        '''
        am = self.am        


        # 计算各均线
        # 计算中长期均线        
        lt_ma_10 = am.sma(10,array=True)
        lt_ma_20 = am.sma(20,array=True)
        lt_ma_30 = am.sma(30,array=True)
        lt_ma_40 = am.sma(40,array=True)
        lt_ma_50 = am.sma(50,array=True)
        lt_ma_60 = am.sma(60,array=True)
        lt_ma_70 = am.sma(70,array=True)
        lt_ma_80 = am.sma(80,array=True)
        lt_ma_90 = am.sma(90,array=True)
        # 计算短期均线
        st_ma_2 = am.sma(2, array=True)
        st_ma_3 = am.sma(3, array=True)
        st_ma_4 = am.sma(4, array=True)
        st_ma_5 = am.sma(5, array=True)
        st_ma_6 = am.sma(6, array=True)
        st_ma_7 = am.sma(7, array=True)
        st_ma_8 = am.sma(8, array=True)
        st_ma_9 = am.sma(9, array=True)
        
        # 中长线趋势判断
        #
        lt_list = [lt_ma_10,lt_ma_20,lt_ma_30,lt_ma_40,lt_ma_50,lt_ma_60,lt_ma_70,lt_ma_80,lt_ma_90]
        lt_list = lt_list[0:self.long_trend_ma_num]  # 只关注部分中长期趋势
        #
        #print(str(sys._getframe().f_lineno)+" long_trend_ma_num:", len(lt_list))
        #
        lt_trend = self.trend_maker(lt_list) 

        lt_probability = []  # 保存多，空，NULL的比例
        duo_count = lt_trend.count("DUO")
        kong_count = lt_trend.count("KONG")
        null_count = lt_trend.count("NULL")
        sub_count = duo_count + kong_count + null_count
        lt_probability.append(duo_count/sub_count) # 分别计算多头所占的比例
        lt_probability.append(kong_count/sub_count) # 分别计算空头所占的比例
        lt_probability.append(null_count/sub_count) # 分别计算非多非空，NULL所占的比例
        #
        #print(str(sys._getframe().f_lineno)+" lt_probability Count:", duo_count, ", ", kong_count, ", ", null_count)
        #print(str(sys._getframe().f_lineno)+" lt_probability DUO:", lt_probability[0], ", ", lt_probability[1], ", ", lt_probability[2])


        # 短线趋势判断
        st_list = [st_ma_2,st_ma_3,st_ma_4,st_ma_5,st_ma_6,st_ma_7,st_ma_8,st_ma_9]
        st_list = lt_list[0:self.short_trend_ma_num]  # 只关注部分短期趋势
        #
        #print(str(sys._getframe().f_lineno)+" short_trend_ma_num:", len(st_list))
        #
        st_trend = self.trend_maker(st_list)

        st_probability = []   # 保存多，空，NULL的比例
        duo_count = st_trend.count("DUO")
        kong_count = st_trend.count("KONG")
        null_count = st_trend.count("NULL")
        sub_count = duo_count + kong_count + null_count
        st_probability.append(duo_count/sub_count) # 分别计算多头所占的比例
        st_probability.append(kong_count/sub_count) # 分别计算空头所占的比例
        st_probability.append(null_count/sub_count) # 分别计算非多非空，NULL所占的比例

        #print(str(sys._getframe().f_lineno)+" st_probability Count:", duo_count, ", ", kong_count, ", ", null_count)
        #print(str(sys._getframe().f_lineno)+" st_probability :", lt_probability[0], ", ", lt_probability[1], ", ", lt_probability[2])

        # 短期涨跌幅比例(short rate: sr_ma_rate)
        if(len(st_list)>1):
            sr_ma_rate = (st_list[-1][-1] - st_list[0][-1])/st_list[0][-1] # 累计涨跌值
        else:
            sr_ma_rate = (st_list[0][-1] - st_list[0][-2])/st_list[0][-2]

        #print(str(sys._getframe().f_lineno)+" sr_ma_rate:", sr_ma_rate, ",short_rate:",self.short_rate)

        sr_ma_probability = sr_ma_rate / self.short_rate # 保存幅度的比例
        duo_sr_probability = 0.0
        kong_sr_probability = 0.0 

        if(sr_ma_probability > 0):
            if(sr_ma_probability >= 1.0):
                duo_sr_probability = 1.0
            else:
                duo_sr_probability = sr_ma_probability
        else:
            if(sr_ma_probability <= -1.0):
                kong_sr_probability = 1.0
            else:
                kong_sr_probability = abs(sr_ma_probability)

        #print(str(sys._getframe().f_lineno)+" sr_ma_probability:", sr_ma_probability)
        
        # 概率积分：针对前面3个条件，可以进行概率假设取值，并进行累加出总的假设概率
        total_duo_probability = 0.0
        total_kong_probability = 0.0

        total_duo_probability = self.k_lt * lt_probability[0] + self.k_st * st_probability[0] + self.K_sr * duo_sr_probability  # 多头的概率
        total_kong_probability = self.k_lt * lt_probability[1] + self.k_st * st_probability[1] + self.K_sr * kong_sr_probability # 空头的概率           
        
        #print("Probability - DUO: ", total_duo_probability, "KONG: ", total_kong_probability, " threshold:",self.kai_probability_threshold)        
        
        if( (self.order_duo_kong.upper() == "D" or self.order_duo_kong.upper() == "D&K") and (total_duo_probability > self.kai_probability_threshold)):            
            #认为是多头，要进行多头操作
            #print("DUO: high = ", self.cur_day_high_price, " close= ", bar.close_price, " Gap= ", self.gap_rate, " Rate= ",((self.cur_day_high_price - bar.close_price) /bar.close_price))
            if(((self.cur_day_high_price - bar.close_price) /bar.close_price) >= self.gap_rate):
                price = bar.close_price + self.kai_ping_price_allowance
                self.kai_cang_order(True,price)
                #print("Kang DUO, price=",price)

        elif ((self.order_duo_kong.upper() == "K" or self.order_duo_kong.upper() == "D&K") and (total_kong_probability > self.kai_probability_threshold)): 
            #认为是空头，要进行空头操作
            #print("KONG: low = ", self.cur_day_low_price, " close= ", bar.close_price, " Gap= ", self.gap_rate, " Rate= ",((self.cur_day_low_price - bar.close_price) /bar.close_price))
            
            if(((bar.close_price - self.cur_day_low_price) /bar.close_price) >= self.gap_rate):
                price = bar.close_price - self.kai_ping_price_allowance
                self.kai_cang_order(False,price)
                #print("Kang KONG, price=",price)
        pass

    def ping_cang_analyse_bar(self, bar:BarData): 
        if self.getWinPips() > 30:
            self.clearOrder()
        pass