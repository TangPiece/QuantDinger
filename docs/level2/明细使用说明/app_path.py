import pandas as pd

tdx_path = 'C:/goldsun/'                           # 通达信 文件夹位置
dfcf_path = 'C:/eastmoney/'                        # 东方财富 文件夹位置
data_path = 'c:/stockdata/'       # 存放下载的东方财富日线资金的文件夹
level2_zlzj_line = data_path + 'dfcfhqzj/'       # 存放下载的东方财富日线资金的文件夹

def display():  # pandas print 对齐
    pd.set_option("display.max_columns", None)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 1000)
    # 以下中文字对齐
    # 第一步 加代码
    pd.set_option("display.unicode.ambiguous_as_wide", True)
    pd.set_option("display.unicode.east_asian_width", True)
    # 第二步 菜单栏--文件--编辑器--配色方案--颜色字体--取消"仅显示等宽字体"--选字体就行，这里选“simhei”。