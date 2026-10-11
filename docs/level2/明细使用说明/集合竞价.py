import pandas as pd

def display():
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 1000)
    pd.set_option("display.unicode.ambiguous_as_wide", True)
    pd.set_option("display.unicode.east_asian_width", True)

display()

class Level2_code:
    def __init__(self, date, code, market, level2_path):
        self.super_amount = 100 * 10000 * 10000  # 超大单 100万元
        self.super_volume = 50 * 10000 * 10000  # 超大单 50万股
        self.big_amount = 20 * 10000 * 10000  # 大单 20万元
        self.big_volume = 10 * 10000 * 10000  # 大单 10万股
        self.date = date
        self.code = code
        self.day = date[0:4] + date[5:7] + date[8:10]
        self.Level2Path = level2_path + self.day + '/'
        self.code = code + '.' + market
        self.fileHq = self.Level2Path + self.code + '/' + '行情.csv'
        self.fileCj = self.Level2Path + self.code + '/' + '逐笔成交.csv'
        self.fileWt = self.Level2Path + self.code + '/' + '逐笔委托.csv'
        self.Hqdata_types = {'万得代码': str, '交易所代码': str, '自然日': str, '时间': str, '成交价': int,
                             '成交量': float,
                             '成交额': float, '成交笔数': int, 'IOPV': str, '成交标志': str, 'BS标志': str,
                             '当日累计成交量': float,
                             '当日成交额': int, '最高价': int, '最低价': int, '开盘价': int, '前收盘': int,
                             '申卖价1': int,
                             '申卖价2': int, '申卖价3': int, '申卖价4': int, '申卖价5': int, '申卖价6': int,
                             '申卖价7': int,
                             '申卖价8': int, '申卖价9': int, '申卖价10': int, '申卖量1': float, '申卖量2': float,
                             '申卖量3': float,
                             '申卖量4': float, '申卖量5': float, '申卖量6': float, '申卖量7': float, '申卖量8': float,
                             '申卖量9': float,
                             '申卖量10': float, '申买价1': int, '申买价2': int, '申买价3': int, '申买价4': int,
                             '申买价5': int,
                             '申买价6': int, '申买价7': int, '申买价8': int, '申买价9': int, '申买价10': int,
                             '申买量1': float,
                             '申买量2': float, '申买量3': float, '申买量4': float, '申买量5': float, '申买量6': float,
                             '申买量7': float,
                             '申买量8': float, '申买量9': float, '申买量10': float, '加权平均叫卖价': int,
                             '加权平均叫买价': int,
                             '叫卖总量': float, '叫买总量': float, '不加权指数': int, '品种总数': int,
                             '上涨品种数': int,
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

        self.Cjdf = pd.read_csv(self.fileCj, encoding='gb18030', dtype=self.Cjdata_types, low_memory=False)  # 个股逐笔成交
        self.amount = self.Cjdf.apply(lambda row: row['成交价格'] * row['成交数量'], axis=1)
        self.Cjdf.insert(loc=6, column='成交金额', value=self.amount)
        self.Cjdf_c = self.Cjdf  # 深圳含撤单数据
        self.Cjdf = self.Cjdf[self.Cjdf['成交价格'] > 0]
        self.Hqdf = pd.read_csv(self.fileHq, encoding='gb18030', dtype=self.Hqdata_types, low_memory=False)  # 个股行情
        self.Wtdf = pd.read_csv(self.fileWt, encoding='gb18030', dtype=self.Wtdata_types, low_memory=False)  # 个股委托

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

    def jd_times(self, start_time='1445', end_time='1501'):  # 阶段资金
        start_time = int(start_time) * 100000
        end_time = int(end_time) * 100000
        cjdf = self.Cjdf
        cjdf['时间_'] = cjdf['时间'].astype(int)
        cjdf = cjdf[cjdf['时间_'] >= start_time]
        cjdf = cjdf[cjdf['时间_'] <= end_time]
        cjdf.drop('时间_', axis=1, inplace=True)
        return cjdf

    def jd_res(self, start_time='1445', end_time='1501'):  # 阶段资金
        start_txt = start_time + '_' + end_time + '_'
        ct_df = self.jd_times(start_time, end_time)
        res = self.cjjd_times_(start_txt, ct_df)
        return res

    def cjjd_times_(self, start_txt, ct_df):
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

    def wt_cj(self):  # 委托明细的成交部分
        cj_buy_groupby = self.Cjdf.groupby('叫买序号').agg({'成交数量': 'sum', '成交金额': 'sum'})  # 成交按叫买序号汇总
        cj_sell_groupby = self.Cjdf.groupby('叫卖序号').agg({'成交数量': 'sum', '成交金额': 'sum'})  # 成交按叫卖序号汇总
        cjbsg = pd.concat([cj_sell_groupby, cj_buy_groupby])
        cjbsg.insert(loc=0, column='交易所委托号', value=cjbsg.index.values)  # 合并买卖成交的交易所委托序号
        wtdf = self.Wtdf[self.Wtdf['委托类型'] != 'D']  # 区除D 类的撤单部分
        wtcjdf = pd.merge(wtdf, cjbsg, left_on='交易所委托号', right_on='交易所委托号', how='inner')  # 成交的委托明细
        wtcjdf['委托金额'] = wtcjdf['委托数量'] * wtcjdf['委托价格']
        # 委托金额和成交金额不等的为主动成交 或主动卖出。这样理解对吗 ? 少了部分，如果是大单那就差不多。
        return wtcjdf

    def l1_number(self):  # 日线 成交额， 成交量
        amount = self.Cjdf['成交金额'].values.sum() / 100000000
        volume = self.Cjdf['成交数量'].values.sum() / 10000
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
        wtcj_df = wtcj[(wtcj['委托金额'] <= 40000 * 10000) & (wtcj['委托数量'] <= 20000)]
        return wtcj_df

    def buy_sell_temp_volume(self, amount_, volume_):
        wtcj_df = self.wtcj_temp(amount_, volume_)
        buy_volume = wtcj_df[wtcj_df['委托代码'] == 'B']['成交数量'].values.sum() / 100000000
        sell_volume = wtcj_df[wtcj_df['委托代码'] == 'S']['成交数量'].values.sum() / 100000000
        return buy_volume, sell_volume

    def buy_sell_mean_price(self, amount_, volume_):  # 均价
        b_v, s_v = self.buy_sell_temp_volume(amount_, volume_)
        b_a, s_a = self.buy_sell_temp_amount(amount_, volume_)
        b_m = 0
        s_m = 0
        if b_v > 0:
            b_m = round(b_a / b_v / 10000, 2)
        if s_v > 0:
            s_m = round(s_a / s_v / 10000, 2)
        return b_m, s_m

    def super_buy_sell_mean_price(self):  # 超大单买卖均价
        return self.buy_sell_mean_price(amount_=self.super_amount, volume_=self.super_volume)

    def big_buy_sell_mean_price(self):  # 大单买卖均价
        return self.buy_sell_mean_price(amount_=self.big_amount, volume_=self.big_volume)

    def buy_sell_temp_amount(self, amount_, volume_):
        wtcj_df = self.wtcj_temp(amount_, volume_)
        wtcj_buy = wtcj_df[wtcj_df['委托代码'] == 'B']['成交金额'].values.sum() / 100000000
        wtcj_sell = wtcj_df[wtcj_df['委托代码'] == 'S']['成交金额'].values.sum() / 100000000
        return wtcj_buy, wtcj_sell

    def super_buy_sell(self):  # 日线 超级买卖金额
        return self.buy_sell_temp_amount(amount_=self.super_amount, volume_=self.super_volume)

    def big_buy_sell(self):  # 日线 大单买卖金额
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
        s_b_m_p, s_s_m_p = self.super_buy_sell_mean_price()  # 超级大单买入和卖出均价
        b_b_m_p, b_s_m_p = self.big_buy_sell_mean_price()  # 大单买入和卖出均价
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

class intergether():
    pass


def sh_so_time(wt):
    # 获取 截止时间
    so_df = wt[wt['委托代码']=='O']
    so_time = int(so_df['时间'].values[0])
    return so_time

def sh_ig(wt, so_time):  # 撤除上交所公司的集合竞价撤单
    # 时间改为整数格式
    wt['时间'] = wt['时间'].values.astype(int)
    # 取截止时间前的数据
    s_wt = wt[wt['时间'] < so_time]
    # 委托买
    b_df = s_wt[s_wt['委托代码']=='B']
    # 委托卖
    s_df = s_wt[s_wt['委托代码']=='S']
    # print(len(s_df))
    # 委托卖撤单
    s_df_d = s_df[s_df['委托类型']=='D']
    #  委托买撤单
    b_df_d = b_df[b_df['委托类型']=='D']

    # 去除 撤单数据
    b_df_B = b_df[~b_df['交易所委托号'].isin(b_df_d['交易所委托号'].values)]
    s_df_S = s_df[~s_df['交易所委托号'].isin(s_df_d['交易所委托号'].values)]
    return b_df_B, s_df_S     # 集合竞价截止时间的有效买入和卖出委托

def sz_so_time(cj):
    w_time = int(cj[cj['成交金额'] > 0]['时间'].values[0])
    return w_time

def sz_ig(wt, cj, w_time):   # 去除深交所的集合竞价撤单
    cj['时间'] = cj['时间'].astype(int)
    cd_df_i = cj[cj['时间'] < w_time]
    b_c_l = [] # 买撤单
    s_c_l = []  # 卖撤单
    for i in range(len(cd_df_i)):
        b_xh = cd_df_i['叫买序号'].values[i]
        s_xh = cd_df_i['叫卖序号'].values[i]
        if b_xh != '0':
            b_c_l.append(b_xh)
        elif s_xh != '0':
            s_c_l.append(s_xh)
    wt['时间'] = wt['时间'].astype(int)
    wt_i = wt[wt['时间'] <= w_time]
    b_df_c = wt_i[wt_i['委托代码'] == 'B']
    s_df_c = wt_i[wt_i['委托代码'] == 'S']
    b_df = b_df_c[~b_df_c['交易所委托号'].isin(b_c_l)]
    s_df = s_df_c[~s_df_c['交易所委托号'].isin(s_c_l)]
    return b_df,s_df

def nor_ig(b_df_B, s_df_S):     # 普通委托集合竞价计算
    v_max = 0
    price = 0
    max_b = b_df_B['委托价格'].values.max()
    min_b = b_df_B['委托价格'].values.min()

    max_s = s_df_S['委托价格'].values.max()
    min_s = s_df_S['委托价格'].values.min()

    if max_b >= min_s:       # 最高买入价大于最低卖出价，有集合竞价
        for i in range(int((max_b - min_b)/100)):
            price_ = 100 * (i + min_b/100)
            b_df_i_v = b_df_B[b_df_B['委托价格'] >= price_]['委托数量'].values.sum()
            s_df_i_v = s_df_S[s_df_S['委托价格'] <= price_]['委托数量'].values.sum()
            if b_df_i_v > s_df_i_v:
                v_min_ = s_df_i_v
            else:
                v_min_ = b_df_i_v
            if v_max == 0:
                v_max = v_min_
                price = price_
            else:
                if v_min_ >= v_max:
                    v_max = v_min_
                    price = price_
                else:
                    price = 100 * (i - 1 +  min_b/100)
                    break

    return price, v_max

def sh_in_dict_df(wt, w_time, t_l = 5000*12):  # 全时段分析获得9点15分到25分的集合竞价 df
    in_dict_list = []
    in_i_s = {'price': '', 'volume': ''}
    ti_l = []
    for ti in range(91500000, w_time, t_l):
        ti_l.append(ti)
    ti_l.append(w_time-1)
    for ti in ti_l:
        b_df_i, s_df_i = sh_ig(wt, ti)
        if len(b_df_i) > 0 and len(s_df_i) > 0:
            p_i, v_i = nor_ig(b_df_i, s_df_i)
            in_i = {'price': int(p_i), 'volume': int(v_i)}
            if in_i_s != in_i:
                in_i_s = in_i
                up_d = in_i_s.copy()
                up_d.update({'time': str(ti)})
                in_dict_list.append(up_d)
    df = pd.DataFrame(in_dict_list)
    df = df.loc[:, ['time', 'price', 'volume']]
    return df

def sz_in_dict_df(wt, cj, w_time, t_l = 5000*12):  # 全时段分析获得9点15分到25分的集合竞价 df
    in_dict_list = []
    in_i_s = {'price': '', 'volume': ''}
    ti_l = []
    for ti in range(91500000, w_time, t_l):
        ti_l.append(ti)
    ti_l.append(w_time-1)
    for ti in ti_l:
        b_df_i, s_df_i = sz_ig(wt, cj, ti)
        if len(b_df_i) > 0 and len(s_df_i) > 0:
            p_i, v_i = nor_ig(b_df_i, s_df_i)
            in_i = {'price': int(p_i), 'volume': int(v_i)}
            if in_i_s != in_i:
                in_i_s = in_i
                up_d = in_i_s.copy()
                up_d.update({'time': str(ti)})
                in_dict_list.append(up_d)
    df = pd.DataFrame(in_dict_list)
    df = df.loc[:, ['time', 'price', 'volume']]
    return df

def lxjhjj(code, date, market, level2_path, frequence=5000*12):
    app = Level2_code(code=code, date=date, market=market, level2_path=level2_path)
    wt = app.Wtdf
    cj = app.Cjdf_c         # 含开盘撤单的数据
    in_df = pd.DataFrame()
    if market == 'sh':
        w_time = sh_so_time(wt)
        in_df = sh_in_dict_df(wt, w_time, t_l=frequence)
    elif market == 'sz':
        w_time = sz_so_time(cj)
        in_df = sz_in_dict_df(wt, cj, w_time, t_l=frequence)
    return in_df

if __name__ == '__main__':
    # code = '003023'
    # market = 'sz'           # 很多代码，市场是哪个不容易分清
    code = '600851'
    market = 'sh'           # 很多代码，市场不易分清
    date = '2026-04-20'
    frequence = 3000 * 1     # 集合竞价计算频率 单位 毫秒
    level2_path = 'd:/'
    igdf = lxjhjj(code, date, market, level2_path, frequence)
    print(igdf)

    L2c = Level2_code(date=date, code=code, market=market, level2_path=level2_path)
    print('逐笔委托读取')
    wt = L2c.Wtdf
    print(wt.head(n=5))
    print(wt.columns)
    print('逐笔成交读取')
    cj = L2c.Cjdf
    print(cj.head(n=5))
    print(cj.columns)
    print('行情读取')
    hq = L2c.Hqdf
    print(hq[1000:1010])
    print(hq.columns)
    print('日线数据汇总')
    df = L2c.report_res()
    print(pd.DataFrame([df]))

    print('# 开盘数据')
    print(pd.DataFrame([L2c.open_res()]))
    print('# 收盘数据')
    ctdf = L2c.open_res(cj_time='1500')
    print(pd.DataFrame([ctdf]))
    print('# 任意一分钟数据')
    cj_time = '1025'
    df_t1 = L2c.open_res(cj_time=cj_time)
    print(pd.DataFrame([df_t1]).columns)
    print(pd.DataFrame([df_t1]))
    print('# 任意时段数据')
    df_t2 = L2c.jd_res(start_time='0935', end_time='0940')
    print(pd.DataFrame([df_t2]).columns)
    print(pd.DataFrame([df_t2]))

    print('# 某小时线数据')
    df_t3 = L2c.jd_res(start_time='1030', end_time='1130')
    print(pd.DataFrame([df_t3]))
    # 日线数据
    df_day = L2c.jd_res(start_time='0925', end_time='1500')
    print(pd.DataFrame([df_day]).columns)

    start_trade = 92600100
    wt['时间_'] = wt['时间'].values.astype(int)
    wt['委托价格_'] = wt['委托价格'].values.astype(int)
    wt['委托数量_'] = wt['委托数量'].values.astype(int)
    df = wt[wt['时间_'] <= start_trade]
