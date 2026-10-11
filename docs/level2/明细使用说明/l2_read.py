import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)
pd.set_option("display.width", 1000)
# 以下中文字对齐
# 第一步 加代码
pd.set_option("display.unicode.ambiguous_as_wide", True)
pd.set_option("display.unicode.east_asian_width", True)


# 第二步 菜单栏--文件--编辑器--配色方案--颜色字体--取消"仅显示等宽字体"--选字体就行，这里选“simhei”。

class Level2_code:
    def __init__(self, date, code, level2_path):
        self.super_amount = 100 * 10000 * 10000           # 超大单 100万元
        self.super_volume = 50 * 10000 * 10000            # 超大单 50万股
        self.big_amount = 20 * 10000 * 10000           # 大单 20万元
        self.big_volume = 10 * 10000 * 10000            # 大单 10万股
        self.date = date
        self.code = code
        self.day = date[0:4] + date[5:7] + date[8:10]
        self.Level2Path = level2_path + self.day + '/'
        if code[0] == '6' or code[0] == '9':
            self.code = code + '.SH'
        else:
            self.code = code + '.SZ'
        self.fileHq = self.Level2Path + self.code + '/' + '行情.csv'
        self.fileCj = self.Level2Path + self.code + '/' + '逐笔成交.csv'
        self.fileWt = self.Level2Path + self.code + '/' + '逐笔委托.csv'
        self.Hqdata_types = {'万得代码': str, '交易所代码': str, '自然日': str, '时间': str, '成交价': int, '成交量': float,
                      '成交额': float, '成交笔数': int, 'IOPV': str, '成交标志': str, 'BS标志': str, '当日累计成交量': float,
                      '当日成交额': int, '最高价': int, '最低价': int, '开盘价': int, '前收盘': int, '申卖价1': int,
                      '申卖价2': int, '申卖价3': int, '申卖价4': int, '申卖价5': int, '申卖价6': int, '申卖价7': int,
                      '申卖价8': int, '申卖价9': int, '申卖价10': int, '申卖量1': float, '申卖量2': float, '申卖量3': float,
                      '申卖量4': float, '申卖量5': float, '申卖量6': float, '申卖量7': float, '申卖量8': float, '申卖量9': float,
                      '申卖量10': float, '申买价1': int, '申买价2': int, '申买价3': int, '申买价4': int, '申买价5': int,
                      '申买价6': int, '申买价7': int, '申买价8': int, '申买价9': int, '申买价10': int, '申买量1': float,
                      '申买量2': float, '申买量3': float, '申买量4': float, '申买量5': float, '申买量6': float, '申买量7': float,
                      '申买量8': float, '申买量9': float, '申买量10': float, '加权平均叫卖价': int, '加权平均叫买价': int,
                      '叫卖总量': float, '叫买总量': float,'不加权指数': int, '品种总数': int, '上涨品种数': int,
                      '下跌品种数': int, '持平品种数': int, 'Unnamed: 66': str}
        self.Cjdata_types = {'万得代码': str, '交易所代码': str, '自然日': str, '时间': str, '成交编号': str,
                             '成交代码': str, '委托代码': str, 'BS标志': str, '成交价格': int, '成交数量': float,
                             '叫卖序号': str, '叫买序号': str, 'Unnamed: 12': str}
        self.Wtdata_types = {'万得代码': str, '交易所代码': str, '自然日': str, '时间': str, '委托编号': str,
                             '交易所委托号': str, '委托类型': str, '委托代码': str, '委托价格': int,
                             '委托数量': float, 'Unnamed: 10': str}
        # print('委托编号' , set(wt['委托编号'].values))      # {'0'}            {'0'}
        # # Side	OrderBSFlag	买卖方向：沪市为B – 买单；S – 卖深市为1 - 买；2 - 卖
        # print('委托代码' , set(wt['委托代码'].values))      # {'B', 'S'}       {'J', 'S', 'C', 'B', 'I', 'O'}
        # # 委托类别：沪市为A – 委托订单（增加）；D – 委托订单（删除）深市为1-市价；2-限价；U - 本方最优
        # print('委托类型' , set(wt['委托类型'].values))      # {'U', '0', '1'}  {'S', 'A', 'D'}

        self.Cjdf = pd.read_csv(self.fileCj, encoding='gb18030', dtype=self.Cjdata_types, low_memory=False)   # 个股逐笔成交
        self.amount = self.Cjdf.apply(lambda row: row['成交价格'] * row['成交数量'], axis=1)
        self.Cjdf = self.Cjdf[self.Cjdf['成交价格'] > 0]
        self.Cjdf.insert(loc=6, column='成交金额', value=self.amount)
        self.Hqdf = pd.read_csv(self.fileHq, encoding='gb18030', dtype=self.Hqdata_types, low_memory=False)   # 个股行情
        self.Wtdf = pd.read_csv(self.fileWt, encoding='gb18030', dtype=self.Wtdata_types, low_memory=False)   # 个股委托
    
    def cj_time(self, cj_time='925'):  # 示例为分钟级 如 0930 如 1120等 925为开盘竞价
        return self.Cjdf[self.Cjdf['时间'].str.match(r'^' + cj_time + '.*') == True]
    
    def open_res(self, cj_time='925'):  # 开盘或收盘或某一分钟的level2数据
        start_txt = cj_time + '_'
        if cj_time == '925':
            start_txt = 'open_'
        elif cj_time == '1500':
            start_txt = 'close_'
        ct_df = self.cj_time(cj_time=cj_time)
        res = self.cjjd_times_(start_txt, ct_df)
        return res
    
    def jd_times(self, start_time='1445', end_time='1501'):      # 阶段资金
        start_time = int(start_time) * 100000
        end_time = int(end_time) * 100000
        cjdf = self.Cjdf
        cjdf['时间'] = cjdf['时间'].astype(int)
        cjdf = cjdf[cjdf['时间'] >= start_time]
        cjdf = cjdf[cjdf['时间'] <= end_time]
        cjdf['时间'] = cjdf['时间'].astype(str)
        return cjdf
    
    def jd_res(self, start_time='1445', end_time='1501'):  # 阶段资金
        start_txt = start_time + '_' + end_time + '_'
        ct_df = self.jd_times(start_time, end_time)
        res = self.cjjd_times_(start_txt, ct_df)
        return res
    
    def cjjd_times_(self, start_txt,  ct_df):
        res = {}
        if len(ct_df) > 0:
            volume_sum = ct_df['成交数量'].sum() / 10000
            amount_sum = ct_df['成交金额'].sum() / 10000 / 10000
            cj_price_values = ct_df['成交价格'].values
            res[start_txt + 'open'] = cj_price_values[0] / 10000
            res[start_txt + 'close'] = cj_price_values[-1] / 10000
            res[start_txt + 'high'] = cj_price_values.max() / 10000
            res[start_txt + 'low'] = cj_price_values.min() / 10000
            res[start_txt + 'volume'] = round(volume_sum, 2)
            res[start_txt + 'amount'] = round(amount_sum, 2)
            sell_ct_group = ct_df.groupby('叫卖序号')
            res['卖委托数'] = len(sell_ct_group)
            sell_amout_sum = sell_ct_group.agg('成交金额').sum()
            super_sell_amount_sum = sell_amout_sum[sell_amout_sum > self.super_amount].sum() / 10000 / 10000
            big_sell_amount_sum = sell_amout_sum[sell_amout_sum > self.big_amount].sum() / 10000 / 10000
            buy_ct_group = ct_df.groupby('叫买序号')
            buy_amout_sum = buy_ct_group.agg('成交金额').sum()
            res['买委托数'] = len(buy_ct_group)
            super_buy_amount_sum = buy_amout_sum[buy_amout_sum > self.super_amount].sum() / 10000 / 10000
            big_buy_amount_sum = buy_amout_sum[buy_amout_sum > self.big_amount].sum() / 10000 / 10000
            res[start_txt + 'super_sell'] = round(super_sell_amount_sum, 2)
            res[start_txt + 'super_buy'] = round(super_buy_amount_sum, 2)
            res[start_txt + 'big_sell'] = round(big_sell_amount_sum, 2)
            res[start_txt + 'big_buy'] = round(big_buy_amount_sum, 2)
        return res

    
    def wt_cj(self):         # 委托明细的成交部分
        cj_buy_groupby = self.Cjdf.groupby('叫买序号').agg({'成交数量': 'sum', '成交金额': 'sum'})      # 成交按叫买序号汇总
        cj_sell_groupby = self.Cjdf.groupby('叫卖序号').agg({'成交数量': 'sum', '成交金额': 'sum'})     # 成交按叫卖序号汇总
        cjbsg = pd.concat([cj_sell_groupby, cj_buy_groupby])
        cjbsg.insert(loc=0, column='交易所委托号', value=cjbsg.index.values)  # 合并买卖成交的交易所委托序号
        wtdf = self.Wtdf[self.Wtdf['委托类型']!='D']     # 区除D 类的撤单部分
        wtcjdf = pd.merge(wtdf, cjbsg, left_on='交易所委托号', right_on='交易所委托号', how='inner')  #成交的委托明细
        wtcjdf['委托金额'] = wtcjdf['委托数量'] * wtcjdf['委托价格']
        # 委托金额和成交金额不等的为主动成交 或主动卖出。这样理解对吗 ? 少了部分，如果是大单那就差不多。
        return wtcjdf
    
    def l1_number(self):       # 日线 成交额， 成交量
        amount = self.Cjdf['成交金额'].values.sum()/100000000
        volume = self.Cjdf['成交数量'].values.sum()/10000
        cj_price_values = self.Cjdf['成交价格'].values
        open = cj_price_values[0] / 10000
        close = cj_price_values[-1] / 10000
        high = cj_price_values.max() / 10000
        low = cj_price_values.min() / 10000
        res = {'close': close, 'open': open, 'high': high, 'low': low, 'amount': round(amount, 2), 'volume': volume}
        return res
    def wtcj_temp(self, amount_, volume_):
        wtcj = self.wt_cj()
        wtcj_df = wtcj[(wtcj['委托金额'] >= amount_) | (wtcj['委托数量'] >= volume_)]
        return wtcj_df
    def wtcj_small(self):  # 小单成交
        wtcj = self.wt_cj()
        wtcj_df =  wtcj[(wtcj['委托金额'] <= 40000*10000) & (wtcj['委托数量'] <= 20000)]
        return wtcj_df
    def buy_sell_temp_volume(self, amount_, volume_):
        wtcj_df = self.wtcj_temp(amount_, volume_)
        buy_volume = wtcj_df[wtcj_df['委托代码'] == 'B']['成交数量'].values.sum()/100000000
        sell_volume = wtcj_df[wtcj_df['委托代码'] == 'S']['成交数量'].values.sum() / 100000000
        return buy_volume, sell_volume
    def buy_sell_mean_price(self, amount_, volume_):  # 均价
        b_v, s_v = self.buy_sell_temp_volume(amount_, volume_)
        b_a, s_a = self.buy_sell_temp_amount(amount_, volume_)
        b_m = 0
        s_m = 0
        if b_v > 0:
            b_m = round(b_a/b_v/10000, 2)
        if s_v > 0:
            s_m = round(s_a/s_v/10000, 2)
        return b_m, s_m
    def super_buy_sell_mean_price(self):         # 超大单买卖均价
        return self.buy_sell_mean_price(amount_=self.super_amount, volume_=self.super_volume)
    def big_buy_sell_mean_price(self):         # 大单买卖均价
        return self.buy_sell_mean_price(amount_=self.big_amount, volume_=self.big_volume)
    def buy_sell_temp_amount(self, amount_, volume_):
        wtcj_df = self.wtcj_temp(amount_, volume_)
        wtcj_buy = wtcj_df[wtcj_df['委托代码'] == 'B']['成交金额'].values.sum()/100000000
        wtcj_sell = wtcj_df[wtcj_df['委托代码'] == 'S']['成交金额'].values.sum()/100000000
        return wtcj_buy, wtcj_sell
    def super_buy_sell(self):  # 日线 超级买卖金额
        return self.buy_sell_temp_amount(amount_=self.super_amount, volume_=self.super_volume)
    def big_buy_sell(self):    # 日线 大单买卖金额
        return self.buy_sell_temp_amount(amount_=self.big_amount, volume_=self.big_volume)
    def b_s_volume_mean(self):  # 平均买卖委托单大小
        # 成交委托均买
        # 成交委托均卖
        # 成交委托均量
        wtcj = self.wt_cj()
        if len(wtcj) == 0:
            print('委托单为零:', self.code)
            return 0, 0, 0, 0
        else:
            if len(wtcj) == 0:
                cjjl = 0
            else:
                cjjl = round(wtcj['委托数量'].values.sum() / len(wtcj), 0)
            buy_cj = wtcj[wtcj['委托代码'] == 'B']
            sell_cj = wtcj[wtcj['委托代码'] == 'S']
            if len(buy_cj) == 0:
                buy_jl = 0
            else:
                buy_jl = round(buy_cj['委托数量'].values.sum() / len(buy_cj), 0)
            if len(sell_cj) == 0:
                sell_jl = 0
            else:
                sell_jl = round(sell_cj['委托数量'].values.sum() / len(sell_cj), 0)
            if sell_jl == 0:
                wtjlb = 0
            else:
                wtjlb = round(100 * (buy_jl / sell_jl - 1), 2)
    
            return cjjl, buy_jl, sell_jl, wtjlb
        
    def report_res(self):
        xx = {}
        xx['date'] = self.date
        xx['code'] = self.code[0:6]
        l1_pav = self.l1_number()
        d_amount = l1_pav['amount']
        if d_amount == 0:
            d_amount = 0.00000001
        xx['open'] = l1_pav['open']
        xx['close'] = l1_pav['close']
        xx['high'] = l1_pav['high']
        xx['low'] = l1_pav['low']
        xx['amount'] = d_amount
        xx['volume'] = l1_pav['volume']
        super_buy, super_sell = self.super_buy_sell()
        xx['super_buy'] = round(super_buy, 2)
        xx['supbl'] = round(100 * super_buy / d_amount, 2)
        xx['super_sell'] = round(super_sell, 2)
        xx['supbsl'] = round(100 * (super_buy - super_sell) / d_amount, 1)
        big_buy, big_sell = self.big_buy_sell()
        xx['big_buy'] = round(big_buy, 2)
        xx['bbl'] = round(100 * big_buy / d_amount, 2)
        xx['big_sell'] = round(big_sell, 2)
        xx['bsl'] = round(100 * (big_buy - big_sell) / d_amount, 1)
        cjjl, buy_jl, sell_jl, wtjlb = self.b_s_volume_mean()
        xx['委托均买'] = buy_jl
        xx['委托均卖'] = sell_jl
        xx['委托均量'] = cjjl
        xx['委托均量比'] = wtjlb
        s_b_m_p, s_s_m_p = self.super_buy_sell_mean_price()   # 超级大单买入和卖出均价
        b_b_m_p, b_s_m_p = self.big_buy_sell_mean_price()   # 大单买入和卖出均价
        xx['超大买均价'] = s_b_m_p
        xx['超大卖均价'] = s_s_m_p
        xx['大单买均价'] = b_b_m_p
        xx['大单卖均价'] = b_s_m_p
        res = xx.copy()

        res.update(self.open_res(cj_time='925'))
        res.update(self.open_res(cj_time='1500'))
        res.update(self.jd_res(start_time='1445', end_time='1500'))
        res.update(self.jd_res(start_time='925', end_time='945'))
        return res
        
        

if __name__ == '__main__':
    
    level2_path = 'e:/'    # ，某日的level2 文件目录

    date = '2025-12-30'
    code ='000001'

    L2c = Level2_code(date=date, code=code, level2_path=level2_path)
    df = L2c.Wtdf
    print('委托示意')
    print(df[8000:8005])
    df = L2c.Cjdf
    print('成交示意')
    print(df[2000:2005])
    df = L2c.Hqdf
    print('行情示意')
    print(df[2000:2005])

    print('开盘集合竞价成交资金汇总')
    print(L2c.open_res())
    print('收盘集合竞价成交资金情况')
    ctdf = L2c.open_res(cj_time='1500')
    print(ctdf)

    print('某一分钟分钟线和资金情况示意')
    print(L2c.open_res(cj_time='1120'))