import sys
import time
import zmq
from datetime import datetime
import pandas as pd
import numpy as np
from PyQt5 import sip
from PyQt5.QtWidgets import *
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import *
from PyQt5.QtGui import QPicture, QPainter
from PyQt5.QtCore import QPointF, QRectF
import pyqtgraph as pg
import configparser
import os

##################### global Variable##############################

AcctNameDict = {}

priceType = {}
priceType['1'] = "AnyPrice"
priceType['2'] = "LimitPrice"
priceType['u'] = "Unknown"
priceType

directionType = {}
directionType['0'] = "Buy"
directionType['1'] = "Sell"
directionType['u'] = "Unknown"
directionType

OpenCloseFlag = {}
OpenCloseFlag['0'] = "Open"
OpenCloseFlag['1'] = "Close"
OpenCloseFlag['3'] = "CloseToday"
OpenCloseFlag['4'] = "CloseYesterday"
OpenCloseFlag['u'] = "Unknown"
OpenCloseFlag

hedgeFlag = {}
hedgeFlag['u'] = "Unknown"
hedgeFlag['1'] = "Speculate"
hedgeFlag['2'] = "Arbitrage"
hedgeFlag

orderStatus = {}
orderStatus['1'] = "New"
orderStatus['2'] = "Accepted"
orderStatus['3'] = "Rejected"
orderStatus['4'] = "Cancelling"
orderStatus['5'] = "Canceled"
orderStatus['6'] = "PartTradedQueueing"
orderStatus['7'] = "PartTradedNotQueueing"
orderStatus['8'] = "AllTraded"
orderStatus['u'] = "Unknown"
orderStatus


#########################################################################################################

################################### Necessary Functions #################################################

#### 获取账户的用户名信息
def GetAcctName():
    tb = pd.read_csv("depend/accountMap.txt", header=None)
    tb.index = tb[0]
    tb = tb[[1]]
    tb.index.name = None
    tb_dict = tb.to_dict()
    tb_dict = tb_dict[1]

    return tb_dict


## 从 yahoo 下载数据
def get_stock_history_from_yahoo(ticker="NFLX"):
    urlstr = "https://finance.yahoo.com/quote/{0}/history?p={0}".format(ticker)
    hdata = pd.read_html(urlstr)[0][:-1]
    hdata = hdata.set_index('Date')
    hdata.index = pd.to_datetime(hdata.index)
    hdata = hdata.astype('d')
    hdata.columns = ['Open', 'High', 'Low', 'Close', 'AdjClose', 'Volume']
    hdata_reindexed = hdata.reset_index()
    valid_set = hdata_reindexed.sort_values(by='Date').reset_index(drop=True)
    return valid_set

## 从本地下载数据
def get_stock_history_from_csv(path="nflx.csv"):
    temp = pd.read_csv(path, index_col=0)
    valid_set = temp.sort_values(by='Date').reset_index(drop=True)
    return valid_set

## 模拟数据流，逐条获取数据
def get_stock_info():
    global valid_tuple_list
    if len(valid_tuple_list) > 0:
        temp = valid_tuple_list[0]
        valid_tuple_list = valid_tuple_list[1:]
        return temp


# ## 获取config
# def read_config():
#     config = pd.read_csv("./depend/socket.txt", header=None)
#     return list(config[0])

#########################################################################################################

################################### Self-design classes #################################################
###Cedar Order
class Order(object):
    m_OrderRef = 0;  #### Order ref no, unique for each order in exchange
    m_RequestID = 0;  ##/< Request id, unique for each strategy
    m_OrderSysID = "";  ##/< Order sys id, used by CTP, according to CTP documentation, It's quicker to use this id when cancelling an order
    m_ProdID = "";  ##/< Product id
    m_ExchID = "";  ##/< Exchange id
    m_PriceType = 'u';  ##/< Price type, refer to \ref PriceTypeGroup
    m_Direction = 'u';  ##/< Order direction, refer to \ref DirectionGroup
    m_CombOffsetFlag = 'u';  ##/< Offest flag, refer to \ref OffsetFlagGroup
    m_CombHedgeFlag = 'u';  ##/< Hedge flag, refer to \ref HedgeFlagGroup
    m_LimitPrice = 0;  ##/< Limit price
    m_VolOriginal = 0;  ##/< Original volume of this order
    m_VolRemaining = 0;  ##/< Remaining volume of this order
    m_VolTraded = 0;  ##/< Traded volume of this order, updated by OnRtnOrder
    m_VolConfirmTraded = 0;  ##/< Confirmed traded volume of this order, updated by OnRtnTrade
    m_Status = 'u';  ##/< Order status, refer to \ref OrderStatusGroup
    m_ChaseTimes = 0;  ##/< The times of chasing this order
    m_SequenceNo = 0;  ##/< Order sequence no, updated by exchange

    def fill_value(msg):
        elems = msg.split(',')
        m_OrderRef = int(elems[0])
        m_RequestID = int(elems[1])
        m_OrderSysID = elems[2]
        m_ProdID = elems[3]
        m_ExchID = elems[4]
        m_PriceType = elems[5]
        m_Direction = elems[6]
        m_CombOffsetFlag = elems[7]
        m_CombHedgeFlag = elems[8]
        m_LimitPrice = float(elems[9])
        m_VolOriginal = int(elems[10])
        m_VolRemaining = int(elems[11])
        m_VolTraded = int(elems[12])
        m_VolConfirmTraded = int(elems[13])
        m_Status = elems[14]
        m_ChaseTimes = int(elems[15])
        m_SequenceNo = int(elems[16])


###Cedar Request
class Request(object):
    rqAcct = 0;
    rqInstrument = "";
    rqBatchID = "";
    rqid = 0;
    rqDirection = 'u';
    rqOrderSize = 0;
    tradedVol = 0;
    tradedAvgPrice = 0;
    fillRate = 0;
    referencePrice = 0;

    def fill_value(msg):
        elems = msg.split(',')
        rqAcct = int(elems[0])
        rqInstrument = elems[1]
        rqBatchID = elems[2]
        rqid = int(elems[3])
        rqDirection = elems[4]
        rqOrderSize = int(elems[5])
        tradedVol = int(elems[6])
        tradedAvgPrice = float(elems[7])
        fillRate = float(elems[8])
        referencePrice = float(elems[9])

## Batch Manager 类，负责管理batch
class BatchManager():

    def __init__(self):
        self.BuyValuePerRQID = {}
        self.SellValuePerRQID = {}
        self.BuyTotalValuePerRQID = {}
        self.SellTotalValuePerRQID = {}
        self.AcctID = 0

    def bookAcctID(self, acct):
        self.AcctID = acct

    def bookTradedValue(self, RQID, value):
        if (value > 0):
            self.BuyValuePerRQID[RQID] = value
            # print("BUY: %f"%(self.BuyValuePerRQID[RQID]))
        else:
            self.SellValuePerRQID[RQID] = value
            # print("SELL: %f"%(self.SellValuePerRQID[RQID]))

    def bookTotalValue(self, RQID, value):
        if (value > 0):
            self.BuyTotalValuePerRQID[RQID] = value
            # print("BUY: %f"%(self.BuyValuePerRQID[RQID]))
        else:
            self.SellTotalValuePerRQID[RQID] = value
            # print("SELL: %f"%(self.SellValuePerRQID[RQID]))

    def getBuyNotional(self):
        # print("BUY NOTIONAL : ",self.BuyValuePerRQID.values(),sum(self.BuyValuePerRQID.values()))
        boughtNotional = sum(self.BuyValuePerRQID.values())
        totalBuyNotional = sum(self.BuyTotalValuePerRQID.values())
        myFillRate = (boughtNotional / totalBuyNotional) if (totalBuyNotional > 0) else 0
        return [boughtNotional, myFillRate, totalBuyNotional]

    def getSellNotional(self):
        # print("SELL NOTIONAL : ",self.SellValuePerRQID.values(),sum(self.SellValuePerRQID.values()))
        soldNoitional = sum(self.SellValuePerRQID.values())
        totalSellNotional = sum(self.SellTotalValuePerRQID.values())
        myFillRate = soldNoitional / totalSellNotional if ((abs(totalSellNotional)) > 0) else 0
        return [soldNoitional, myFillRate, totalSellNotional]

    def getAcctID(self):
        return self.AcctID;




class DrawRecItem(pg.GraphicsObject):
    def __init__(self, data):
        super().__init__()
        self.LineData = data
        self.color_list = [(217, 194, 234),
                           (58, 135, 162),
                           (196, 62, 244),
                           (147, 223, 153),
                           (103, 182, 144),
                           (194, 22, 47),
                           (22, 182, 89)]
        self.draw_rect()

    def draw_rect(self):

        self.picture = QPicture()
        p1 = QPainter(self.picture)

        ### 画k线图 ##########

        # 设置画pen 颜色，用来画线
        # 颜色代码使用 RGB值，缩写，都可以
        #         p1.setPen(pg.mkPen((0,0,0)))
        #         for i in range(len(self.LineData)):
        #             #画一条最大值最小值之间的线
        #             p1.drawLine(QPointF(i,self.LineData[i][3]),QPointF(i,self.LineData[i][2]))
        #             # 设置画刷颜色
        #             if self.LineData[i][1]>self.LineData[i][4]:
        #                 p1.setBrush(pg.mkBrush('g'))
        #             else:
        #                 p1.setBrush(pg.mkBrush('r'))
        #             p1.drawRect(QRectF(i-0.3,self.LineData[i][1],0.6,self.LineData[i][4]-self.LineData[i][1]))

        #### 画自定义的线 ####################
        #          ## TEST close线
        #         p1.setPen(pg.mkPen(255,0,0))
        #         for i in range(len(self.LineData['TEST'])-1):
        #             p1.drawLine(QPointF(i,self.LineData['TEST'][i][4]),QPointF(i+1,self.LineData['TEST'][i+1][4]))
        count = 0
        for index in self.LineData.keys():
            rand_col = self.color_list[count]
            p1.setPen(pg.mkPen(rand_col))
            for i in range(len(self.LineData[index]) - 1):
                p1.drawLine(QPointF(i, self.LineData[index][i][4]), QPointF(i + 1, self.LineData[index][i + 1][4]))
            count += 1
        # ## FLOW  close线
        # p1.setPen(pg.mkPen(255, 0, 0))
        # for i in range(len(self.LineData['FLOW']) - 1):
        #     p1.drawLine(QPointF(i, self.LineData['FLOW'][i][4]), QPointF(i + 1, self.LineData['FLOW'][i + 1][4]))
        #
        # ## FLML  close线
        # p1.setPen(pg.mkPen(0, 255, 0))
        # for i in range(len(self.LineData['FLML']) - 1):
        #     p1.drawLine(QPointF(i, self.LineData['FLML'][i][4]), QPointF(i + 1, self.LineData['FLML'][i + 1][4]))
        #
        # ## ML  close线
        # p1.setPen(pg.mkPen(0, 0, 255))
        # for i in range(len(self.LineData['ML']) - 1):
        #     p1.drawLine(QPointF(i, self.LineData['ML'][i][4]), QPointF(i + 1, self.LineData['ML'][i + 1][4]))

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QRectF(self.picture.boundingRect())


## 时间轴类 由于时间轴需要是 动态的，并且需要输出的是string型，需要 派生与 AXisItem 重载 tickstring Method
class MyAxisItem(pg.AxisItem):
    def __init__(self, ticks, *args, **kwargs):
        pg.AxisItem.__init__(self, *args, **kwargs)
        self.x_values = [x[0] for x in ticks]
        self.x_strings = [x[1] for x in ticks]

    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            vs = v * scale
            if vs in self.x_values:
                vstr = self.x_strings[np.abs(self.x_values - vs).argmin()]
            else:
                vstr = ''

            strings.append(vstr)
        return strings


##############tab1 线程###########################
class UpdateData(QtCore.QThread):
    requestChanged = QtCore.pyqtSignal(int, int, str)  # rowIndex, msgType,msg

    def run(self):
        #requestChanged = QtCore.pyqtSignal(int, int, str)
        context = zmq.Context()
        sock = context.socket(zmq.SUB)
        sock.setsockopt(zmq.SUBSCRIBE, b"EMS_GUI_SubOda")
        sock.setsockopt(zmq.SUBSCRIBE, b"EMS_GUI_Request")
        sock.setsockopt(zmq.SUBSCRIBE, b"EMS_GUI_Error")
        sock.setsockopt(zmq.HEARTBEAT_IVL, 5000)
        sock.setsockopt(zmq.HEARTBEAT_TIMEOUT, 3000)
        # print("hello")
        sock.connect("tcp://192.168.0.66:15300")
        sock.connect("tcp://117.185.37.175:51336")
        ### DOUBLE RQID Problem

        while True:
            msg = sock.recv()
            msgs = msg.decode("ascii").split("|")
            # msgs= msg.split(',')
            # self.LineDataChanged.emit(2, 2, msgs[0])
            print(msgs[0], msgs[1])
            if (msgs[0] == "EMS_GUI_Request"):
                self.requestChanged.emit(1, 1, msgs[1])
                print(msgs[1])
            elif (msgs[0] == "EMS_GUI_SubOda"):
                self.requestChanged.emit(2, 2, msgs[1])
                print(msgs[1])
            elif (msgs[0] == "EMS_GUI_Error"):
                self.requestChanged.emit(2, 3, msgs[1])
                print(msgs[1])

#### tab2 线程############################
class Update_tab2(QtCore.QThread):
    requestChange = QtCore.pyqtSignal(str, tuple)

    def __init__(self, config, parent=None):
        super(Update_tab2, self).__init__(parent)
        # 设置工作状态与初始num数值
        self.config = config

    def __del__(self):
        # 线程状态改变与线程终止
        self.working = False
        self.wait()

    def run(self):
        context = zmq.Context()
        sock = context.socket(zmq.SUB)
        for i in self.config:
            sock.setsockopt(zmq.SUBSCRIBE, i.encode())

        # 新添一个 HIST 表示符
        sock.setsockopt(zmq.SUBSCRIBE, b"HIST")
        sock.setsockopt(zmq.HEARTBEAT_IVL, 5000)
        sock.setsockopt(zmq.HEARTBEAT_TIMEOUT, 3000)

        ### 需要同时 获取 hist 以及实时数据
        sock.connect("tcp://192.168.0.32:19006")
        sock.connect("tcp://192.168.0.32:19007")
        #         for i in range(100):
        while True:
            #             msg=get_stock_info()
            #             time.sleep(1)
            sss = sock.recv()
            msg = sss.decode("ascii").split(",")
            new_data_collection = []

            #             if msg[0]=='ML':
            #                 print(msg)

            lag = msg[0]
            if lag in self.config:
                new_data_collection.append(msg[1])
                for i in msg[2:]:
                    new_data_collection.append(float(i) * 10000)
                self.requestChange.emit(lag, tuple(new_data_collection))

            if lag == 'HIST':
                new_data_collection.append(msg[1])
                new_data_collection.append(msg[2])
                for i in msg[3:]:
                    new_data_collection.append(float(i) * 10000)
                self.requestChange.emit(lag, tuple(new_data_collection))


#             if msg[0]=='FLOW':
#                 new_data_FLOW.append(msg[1])
#                 for i in msg[2:]:
#                     new_data_FLOW.append(float(i)*10000)
#                 print('FLOW ',new_data_FLOW)

#                 self.requestChange.emit('FLOW',tuple(new_data_FLOW))
#             if msg[0]=='FLML':
#                 new_data_FLML.append(msg[1])
#                 for i in msg[2:]:
#                     new_data_FLML.append(float(i)*10000)
#                 print('FLML ',new_data_FLML)
#                 self.requestChange.emit('FLML',tuple(new_data_FLML))
#             if msg[0]=='ML':
#                 time.sleep(1)
#                 new_data_ML.append(msg[1])
#                 for i in msg[2:]:
#                     new_data_ML.append(float(i)*10000)
#                 print('ML ',new_data_ML)
#                 self.requestChange.emit('ML',tuple(new_data_ML))


#             if msg!= None and msg[0]=='TEST':
#                 #print(tuple(msg[1:]))
#                 self.requestChange.emit('TEST',tuple(msg[1:]))
#                 #self.requestChange.emit('TEST2',('090000',0,0,0))
# #                 #print('ML ',new_data_ML)


###### tab3 线程###########################
class UpdateData_tab3(QtCore.QThread):
    requestChanged = QtCore.pyqtSignal(int, int, list)  # rowIndex, msgType,msg list

    def run(self):
        requestChanged = QtCore.pyqtSignal(int, int, list)
        context = zmq.Context()
        sock = context.socket(zmq.SUB)
        sock.setsockopt(zmq.SUBSCRIBE, b"IND_CONTRIBUTE")
        sock.setsockopt(zmq.SUBSCRIBE, b"TOP_WINNER")
        sock.setsockopt(zmq.SUBSCRIBE, b"TOP_LOSSER")
        sock.setsockopt(zmq.HEARTBEAT_IVL, 5000)
        sock.setsockopt(zmq.HEARTBEAT_TIMEOUT, 3000)
        # print("hello")
        sock.connect("tcp://192.168.0.32:19006")
        ### DOUBLE RQID Problem

        #         for i in range(108):
        while True:
            #             real one
            msg = sock.recv()
            msgs = msg.decode("utf-8").split(",")
            # msgs= msg.split(',')
            # self.LineDataChanged.emit(2, 2, msgs[0])
            # print(msgs)
            if (msgs[0] == "IND_CONTRIBUTE"):
                self.requestChanged.emit(1, 1, msgs[1:])

            elif (msgs[0] == "TOP_WINNER"):
                self.requestChanged.emit(2, 2, msgs[1:])

            elif (msgs[0] == "TOP_LOSSER"):
                self.requestChanged.emit(2, 3, msgs[1:])
            # test one:


#             msgs=get_info()
#             time.sleep(1)
# print(msgs)
#             if(msgs[0] == "IND_CONTRIBUTE"):
#                 self.requestChanged.emit(1,1, msgs[1:])

#             elif(msgs[0] == "TOP_WINNER"):
#                 self.requestChanged.emit(2,2, msgs[1:])

#             elif(msgs[0] == "TOP_LOSSER"):
#                 self.requestChanged.emit(2,3, msgs[1:])

#### tab4 线程############################
class Update_tab4(QtCore.QThread):
    requestChanged = QtCore.pyqtSignal(tuple)

    def __init__(self, parent=None):
        super(Update_tab4, self).__init__(parent)
        # 设置工作状态与初始num数值

    def __del__(self):
        # 线程状态改变与线程终止
        self.working = False
        self.wait()

    def run(self):
        context = zmq.Context()
        sock = context.socket(zmq.SUB)
        sock.setsockopt(zmq.SUBSCRIBE, b'BarraRisk')

        sock.setsockopt(zmq.HEARTBEAT_IVL, 5000)
        sock.setsockopt(zmq.HEARTBEAT_TIMEOUT, 3000)

        sock.connect('tcp://192.168.0.32:19007')
        #         for i in range(100):
        while True:
            #             msg=get_stock_info()
            #             time.sleep(1)
            sss = sock.recv()
            msg = sss.decode("ascii").replace(' ', '').split(",")
            new_data_collection = []

            #             if msg[0]=='ML':
            #                 print(msg)

            lag = msg[1]
            new_data_collection.append(msg[1])
            new_data_collection.append(msg[2])
            new_data_collection.append(float(msg[3]))
            self.requestChanged.emit(tuple(new_data_collection))


## 主基类，是 整个GUI的主窗口，内部含有三个子窗口
class Control_sys_Tab(QTabWidget):
    def __init__(self, parent=None):

        self.LineData = {}
        self.color_list = [(193, 210, 240),
                           (58, 135, 162),
                           (196, 62, 244),
                           (147, 223, 153),
                           (103, 182, 144),
                           (194, 22, 47),
                           (22, 182, 89)]

        self.time_dict = {}

        self.RequestRowKey = {}
        self.OrderRowKey = {}
        self.BatchRowKey = {}  # To manage batch row index
        self.ErrorRowKey = {}  # To manage error row index
        self.BuyBatchValue = {}
        self.SellBatchValue = {}
        self.BatchManagers = {}  # To manage value for each batch
        self.g_CurrRequestRow = 0
        self.g_CurrOrderRow = 0
        self.g_CurrBatchRow = 0
        self.g_CurrErrorRow = 0

        # set config
        self.conf = configparser.ConfigParser()
        self.conf.read('./depend/config.txt')

        # tab3 use
        self.g_cat_row_dict = {}
        self.cat_next_row = 0

        self.g_winner_row_dict = {}
        self.winner_next_row = 0

        self.g_losser_row_dict = {}
        self.losser_next_row = 0

        super().__init__(parent)

        #         # 设置sizepolicy
        #         self.setSizePolicy(QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding,
        #                                                  QtWidgets.QSizePolicy.MinimumExpanding))

        self.setObjectName("Control_system")
        self.resize(1800, 985)
        self.setWindowTitle("实时监控系统")

        # 创建3个选项卡小控件窗口
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        self.tab3 = QWidget()
        self.tab4 = QWidget()

        # 将三个选项卡添加到顶层窗口中
        self.addTab(self.tab1, "交易界面")
        self.addTab(self.tab2, "损益界面")
        self.addTab(self.tab3, "风险分析")
        self.addTab(self.tab4, "Barra分析")

        # 记录tab2 中的数据，后续会从其他类中读取数据，并更新和作图
        config_tab2 = self.conf.get('tab2', 'tab2_lines').split(",")
        for i in config_tab2:
            self.LineData[i] = {}
        self.tab2_work = Update_tab2(config_tab2)

        # tab4 use
        # 对于Barra数据，现计划是不断刷新十行展示数据，那么只需要使用一维map来存储即可 map的key值为策略名，value为顺序的list
        self.Barra_Data={}
        config_tab4=self.conf.get('tab4','table7_lables').split(',')
        for i in config_tab4:
            self.Barra_Data[i]={}
        self.tab4_work=Update_tab4()

        # risk 列表
        self.risk_list=['BETA',"BP","EP","GRO","LEV","LIQ","MOM","NLSIZE","SIZE","VOL"]

        # 每个选项卡自定义的内容
        self.tab1UI()
        self.tab2UI()
        self.tab3UI()
        self.tab4UI()

        self.pushButton.clicked.connect(self.slotStart)

    ################tab1#################################

    def tab1UI(self):
        # 设置主布局
        layout = QHBoxLayout()

        sec_layout = QVBoxLayout()

        # 创建表格窗口1
        self.tableWidget1 = QtWidgets.QTableWidget()
        self.tableWidget1.setRowCount(5000)
        self.tableWidget1.setColumnCount(11)
        self.tableWidget1.setObjectName("tableWidget")
        self.tableWidget1.setAutoFillBackground(True)
        self.tableWidget1.setHorizontalHeaderLabels(
            ["Acct", "Instrument", "BatchID", "RQID", "Direction", "OrderSize", "TradedVol", "AvgPrice", "Notional",
             "FillRate", "RefPrice"])
        for i in range(0, 11):
            self.tableWidget1.horizontalHeaderItem(i).setTextAlignment(Qt.AlignHCenter)
        # self.tableWidget.item(0, 0).setFont(font)

        # 表格窗口2
        self.tableWidget2 = QtWidgets.QTableWidget()
        self.tableWidget2.setRowCount(20000)
        self.tableWidget2.setColumnCount(14)
        self.tableWidget2.setObjectName("tableWidget")
        self.tableWidget2.setAutoFillBackground(True)
        self.tableWidget2.setHorizontalHeaderLabels(
            ["OrderRef", "RequestID", "PriceType", "Direction", "OffsetFlag", "HedgeFlag", "LimitPrice", "VolOriginal",
             "VolRemain", "VolTraded", "VolConfirmed", "Status", "OrderSysID", "ExchID"])
        for i in range(0, 14):
            self.tableWidget2.horizontalHeaderItem(i).setTextAlignment(Qt.AlignHCenter)

        # 表格窗口3
        self.tableWidget3 = QtWidgets.QTableWidget()
        # self.tableWidget3.setTextAlignment(Qt.AlignHCenter)
        self.tableWidget3.setRowCount(500)
        self.tableWidget3.setColumnCount(6)
        # self.tableWidget3.setStyleSheet('background-repeat:repeat;')  #font color
        # self.tableWidget3.setStyleSheet('color:darkblue;')  #font color
        # self.tableWidget3.setStyleSheet('text-align:center;')
        # self.tableWidget3.setStyleSheet('vertical-align:super;')
        # self.tableWidget3.setStyleSheet('background-color:lightblue')
        # self.tableWidget3.horizontalHeader().setStyleSheet('QHeaderView::section{background:gray}')

        self.tableWidget3.setObjectName("tableWidget")
        self.tableWidget3.setAutoFillBackground(True)
        self.tableWidget3.setHorizontalHeaderLabels(
            ["BatchID", "AcctName", "BuyNotional", "SellNotional", "BuyFillRate", "SellFillRate"])
        for i in range(0, 6):
            self.tableWidget3.horizontalHeaderItem(i).setTextAlignment(Qt.AlignHCenter)
            # self.tableWidget3.
        self.tableWidget3.setColumnWidth(0, 150)
        self.tableWidget3.setColumnWidth(1, 150)
        self.tableWidget3.setColumnWidth(2, 100)
        self.tableWidget3.setColumnWidth(3, 100)
        self.tableWidget3.setColumnWidth(4, 100)
        self.tableWidget3.setColumnWidth(5, 100)
        # self.label = QtWidgets.QLabel(self.centralwidget)
        # self.label.setGeometry(QtCore.QRect(360, 70, 300, 50))
        # self.label.setObjectName("label")
        # self.label.setAutoFillBackground(True)
        # self.label.setAlignment(QtCore.Qt.AlignCenter)
        # self.label.setStyleSheet("border-image:url(images/title.png)")

        self.pushButton = QtWidgets.QPushButton()
        # self.pushButton.setMaximumWidth(100)
        self.pushButton.setObjectName("pushButton")
        self.pushButton.setText("开始运行")

        # 添加表单2进 子布局
        sec_layout.addWidget(self.tableWidget2)

        # 添加表单3进 子布局
        sec_layout.addWidget(self.tableWidget3)

        # 添加 按钮 进 子布局
        sec_layout.addWidget(self.pushButton)

        # 添加表单1 进主布局，子布局进主布局
        layout.addWidget(self.tableWidget1)
        layout.addLayout(sec_layout)

        self.tab1.setLayout(layout)

    #################tab2#################################
    ######################################

    ### 测试线程用代码
    def execute(self):
        # 启动线程
        self.tab2_work.start()
        # 线程自定义信号连接的槽函数
        self.tab2_work.requestChange.connect(self.display)

    def display(self, biaoji, new_data):
        # 由于自定义信号时自动传递1个字符串参数，所以在这个槽函数中要接受1个参数
        # print(new_data)

        # 对于现有的 时间戳，如果读取的标识符为 HIST 则不需要绘图，直接添加数据
        if new_data[1] != '0':
            if biaoji == 'HIST':
                # print(new_data)
                self.LineData[new_data[0]][new_data[1]] = tuple(new_data[2:])

            else:

                self.plotData(biaoji, new_data)

    ########################################
    # 定义一个计时器
    #     def timer_start(self):

    #         self.timer = QtCore.QTimer(self)
    #         self.timer.timeout.connect(self.plotData)
    #         self.timer.start(1000)
    #####################################################

    ################绘图用函数############################
    def print_slot(self, event=None):
        if event is None:
            print("事件为空")
        else:

            pos = event[0]  # 鼠标的位置为event的第一个值

            try:
                if self.plt.sceneBoundingRect().contains(pos):

                    # 一个文本项 用来展示十字对应的信息
                    min_len = min(len(self.LineData[k]) for k in self.LineData.keys())
                    max_len = max(len(self.LineData[k]) for k in self.LineData.keys())

                    #                     print(pos)
                    mousePoint = self.plt.plotItem.vb.mapSceneToView(pos)  # 转换鼠标坐标
                    index = int(mousePoint.x())  # 鼠标所处的X轴坐标
                    pos_y = int(mousePoint.y())  # 鼠标所处的Y轴坐标

                    # 当时间线统一时
                    # 需要重定位，定位到最近的曲线
                    # print('max_len ',min_len)
                    if -1 < index < min_len:
                        # print('index ',index)
                        min_index = min(self.LineData, key=lambda k: abs(self.LineData[k][index][4] - pos_y))

                        # 在label中写入HTML
                        self.label.setHtml(
                            "<p style='color:black'><strong>数据源：{0}\
                            <p style='color:black'><strong>时间：{1}</strong></p><p style='color:black'>\
                            开盘：{2}</p><p style='color:black'>\
                            收盘：{3}</p><p style='color:black'>\
                            最高价：<span style='color:red;'>{4}</span></p><p style='color:black'>\
                            最低价：<span style='color:green;'>{5}</span></p>".format(
                                min_index, self.LineData[min_index][index][0], self.LineData[min_index][index][1],
                                self.LineData[min_index][index][4],
                                self.LineData[min_index][index][2], self.LineData[min_index][index][3]))
                        self.label.setPos(mousePoint.x(), mousePoint.y())  # 设置label的位置
                        # print(self.label)

                    # 当时间线不统一时,只显示数据最多的
                    elif min_len < index < max_len:
                        min_index = min(self.LineData, key=lambda k: len(self.LineData[k]))
                        # 在label中写入HTML
                        self.label.setHtml(
                            "<p style='color:black'><strong>数据源：{0}\
                            <p style='color:black'><strong>时间：{1}</strong></p><p style='color:black'>\
                            开盘：{2}</p><p style='color:black'>\
                            收盘：{3}</p><p style='color:black'>\
                            最高价：<span style='color:red;'>{4}</span></p><p style='color:black'>\
                            最低价：<span style='color:green;'>{5}</span></p>".format(
                                min_index, self.LineData[min_index][index][0], self.LineData[min_index][index][1],
                                self.LineData[min_index][index][4],
                                self.LineData[min_index][index][2], self.LineData[min_index][index][3]))
                        self.label.setPos(mousePoint.x(), mousePoint.y())  # 设置label的位置

                    ## 将label添加进 plt
                    self.plt.addItem(self.label)
                    # print(self.plt.listDataItems())
                    # 设置垂直线条和水平线条的位置组成十字光标
                    self.vLine.setPos(mousePoint.x())
                    self.hLine.setPos(mousePoint.y())
            except Exception as e:
                print("error in print_slot")

    ######################################################

    def append_stock_data(self):
        temp = get_stock_info()
        if temp != None:
            self.LineData.append(temp)

    def plotData(self, biaoji, new_data):
           try:
                # print(len(self.LineData))
                #         print(new_data)
                # 添加数据
                if new_data != None and new_data[0] != '0':
                    #             try:
                    # new data 为 tuple形
                    self.LineData[biaoji][new_data[0]] = list(new_data)[1:]
                #             except Exception as e:
                #                 print("error in saving data...")

                # 画图
                # 由于数据图可能会有一个点 传过去所有的历史数据，所以 现在改为dict存储

                # 首先需要对 dict进行排序
                # 首先获得所有 biaoji下的 dict keys 的交集，因为x,y 需要长度相同
                temp = list(self.LineData.keys())
                min_time_list = self.LineData[temp[0]].keys()

                for x in list(self.LineData.keys()):
                    # min_time_list=list(set(min_time_list).intersection(set(self.LineData[x].keys())))
                    min_time_list = list(set(min_time_list).union(set(self.LineData[x].keys())))

                min_time_list = sorted(min_time_list, key=lambda d: pd.to_datetime(d, format="%H%M%S"))

                x = []
                time_out = []
                for time in min_time_list:
                    x.append(self.time_dict[time])
                #         if biaoji=='ML':
                #             print(time_out)

                y = []

                #         #生成绘图时 需要的x轴，y轴
                #         for i in self.LineData[biaoji]:
                #             x.append(self.time_dict[i[0]])
                #             y.append(float(i[3]))

                for i in min_time_list:
                    y.append(float(self.LineData[biaoji][i][3]))

                #         print(x)
                #         if biaoji=='ML':
                #             print(x)

                index = list(self.LineData.keys()).index(biaoji)
                # print(len(self.LineData[biaoji]))
                color_id = list(self.LineData.keys()).index(biaoji)
                # self.plot_line[index].clear()
                self.plot_line[index].setData(x, y, pen=pg.mkPen(self.color_list[color_id], width=3))
                # print(len(self.LineData['TEST2']))
           except Exception as e:
               print("error in plotData")
        ###################################################该部分 代码 为实时更新和删除图片，用于显示自定义类###############################
        #         if new_data != None:
        #             self.LineData[biaoji].append(new_data)

        #             item = DrawRecItem(self.D

        #             ## 清空layout2 以重新插入图片
        #             for i in range(self.layout2.count()):
        #                 self.layout2.itemAt(i).widget().deleteLater()

        #             ## 由于新添了
        #             max_len=max(len(self.LineData[k]) for k in self.LineData.keys())
        #             max_index=max(self.LineData, key=lambda k:len(self.LineData[k]))

        #             index = range(max_len)
        #             time_list = []
        #             for i in index:
        #                 temp = self.LineData[max_index][i][0]
        #                 time_list.append(temp)
        #             ticks = [(i, j) for i, j in zip(index, time_list)]
        #             strAxis = MyAxisItem(ticks, orientation="bottom")
        #             self.plt = pg.PlotWidget(axisItems={'bottom': strAxis})
        #             self.plt2 = pg.PlotWidget()

        #             ## 设置背景颜色
        #             self.plt.setBackground((255, 255, 255))

        #             # 将iTem加入到plotwidget控件中
        #             self.plt.addItem(item)

        #             # 将控件添加到pyqt中
        #             self.layout2.addWidget(self.plt,0,0)

        #             # 添加控件2
        #             #self.layout2.addWidget(self.plt2,0,1)

        #             # 将layout 布局添加到 tab2中
        #             self.tab2.setLayout(self.layout2)

        #             # 设置标签
        #             self.label = pg.TextItem()

        #             self.vLine = pg.InfiniteLine(angle=90, movable=False, )  # 创建一个垂直线条
        #             self.hLine = pg.InfiniteLine(angle=0, movable=False, )  # 创建一个水平线条
        #             self.plt.addItem(self.vLine, ignoreBounds=True)  # 在图形部件中添加垂直线条
        #             self.plt.addItem(self.hLine, ignoreBounds=True)  # 在图形部件中添加水平线条
        #             min_len=min(len(self.LineData[k]) for k in self.LineData.keys())
        # #             if min_len>1:
        # #                 self.move_slot=pg.SignalProxy(self.plt.scene().sigMouseMoved, rateLimit=60, slot=self.print_slot)
#####################################################################################################################################

    def tab2UI(self):
        #         self.timer_start()
        self.layout2 = QGridLayout()
        self.tab2.setLayout(self.layout2)

        # 生成时间轴列表
        int_list = np.arange(6 * 60 * 60+1)
        x_list = []
        temp = pd.date_range('9:00', periods=6 * 60 * 60+1, freq='S')
        for i in temp:
            temp_time = str(i).split()[1].replace(':', '')
            if temp_time[0] == '0':
                temp_time = temp_time[1:]
            x_list.append(temp_time)

        # 生成绘图时需要使用的时间轴
        count = 0
        for x in x_list:
            self.time_dict[x] = count
            count += 1

        ticks = [(i, j) for i, j in zip(int_list, x_list)]
        strAxis = MyAxisItem(ticks, orientation="bottom")

        # 创建画图板
        self.plot_plt = pg.PlotWidget(axisItems={'bottom': strAxis})
        self.plot_plt.addLegend()
        self.plot_plt.showGrid(x=True, y=True)
        self.layout2.addWidget(self.plot_plt)

        len_keys = len(self.LineData.keys())
        # print(self.LineData.keys())
        self.plot_line = [0] * len_keys
        count = 0
        for i in range(len_keys):
            self.plot_line[i] = self.plot_plt.plot([0], [0], pen=self.color_list[i], name=list(self.LineData.keys())[i])

        ## 设置背景色
        self.plot_plt.setBackground((255, 255, 255))
        ## 定位图片显示时的坐标轴
        self.plot_plt.setYRange(max=50, min=-50)
        self.plot_plt.setXRange(min=0, max=21600+1)

        # self.timer_start()
        self.execute()

    def tab3UI(self):

        # 设置主布局
        layout = QHBoxLayout()

        sec_layout = QVBoxLayout()

        # 创建表格窗口1
        self.tableWidget4 = QtWidgets.QTableWidget()
        self.tableWidget4.setRowCount(40)
        fixed_list = self.conf.get('tab3', 'table4_lables').split(',')
        self.tableWidget4.setColumnCount(len(fixed_list))
        self.tableWidget4.setObjectName("tableWidget4")
        self.tableWidget4.setHorizontalHeaderLabels(fixed_list)
        for i in range(0, 40):
            self.tableWidget4.setRowHeight(i, 30)
        for i in range(0, len(fixed_list)):
            self.tableWidget4.horizontalHeaderItem(i).setTextAlignment(Qt.AlignHCenter)
            if (i == 1):
                self.tableWidget4.setColumnWidth(i, 200)
            else:
                self.tableWidget4.setColumnWidth(1, 100)

        # 表格窗口2
        self.tableWidget5 = QtWidgets.QTableWidget()
        self.tableWidget5.setRowCount(3000)
        fixed_list = self.conf.get('tab3', 'table5_lables').split(',')
        self.tableWidget5.setColumnCount(len(fixed_list))
        self.tableWidget5.setObjectName("tableWidget5")
        self.tableWidget5.setAutoFillBackground(True)
        self.tableWidget5.setHorizontalHeaderLabels(fixed_list)
        for i in range(0, 3000):
            self.tableWidget5.setRowHeight(i, 30)
        for i in range(0, len(fixed_list)):
            self.tableWidget5.horizontalHeaderItem(i).setTextAlignment(Qt.AlignHCenter)
            self.tableWidget5.setColumnWidth(i, 180)

        # 表格窗口3
        self.tableWidget6 = QtWidgets.QTableWidget()

        self.tableWidget6.setRowCount(3000)
        fixed_list = self.conf.get('tab3', 'table6_lables').split(',')
        self.tableWidget6.setColumnCount(len(fixed_list))

        self.tableWidget6.setObjectName("tableWidget6")
        self.tableWidget6.setAutoFillBackground(True)

        self.tableWidget6.setHorizontalHeaderLabels(fixed_list)
        for i in range(0, 3000):
            self.tableWidget6.setRowHeight(i, 30)
        for i in range(0, len(fixed_list)):
            self.tableWidget6.horizontalHeaderItem(i).setTextAlignment(Qt.AlignHCenter)
            self.tableWidget6.setColumnWidth(i, 180)

        self.pushButton3 = QtWidgets.QPushButton()
        # self.pushButton.setMaximumWidth(100)
        self.pushButton3.setObjectName("pushButton3")
        self.pushButton3.setText("开始运行")

        # 添加表单2进 子布局
        sec_layout.addWidget(self.tableWidget5)

        # 添加表单3进 子布局
        sec_layout.addWidget(self.tableWidget6)

        # 添加 按钮 进 子布局
        sec_layout.addWidget(self.pushButton3)

        # 添加表单1 进主布局，子布局进主布局
        layout.addWidget(self.tableWidget4)
        layout.addLayout(sec_layout)

        self.tab3.setLayout(layout)
        self.pushButton3.clicked.connect(self.slotStart_tab3)

    def tab4UI(self):

        # 设置布局
        # 由于只需要两个窗口，因此一个布局器即可
        layout = QVBoxLayout()

        self.tableWidget7 = QtWidgets.QTableWidget()
        self.tableWidget7.setRowCount(10)
        self.tab4_lable_list = self.conf.get('tab4', 'table7_lables').split(',')
        self.tableWidget7.setColumnCount(len(self.tab4_lable_list))
        self.tableWidget7.setObjectName("tableWidget7")

        self.tableWidget7.setHorizontalHeaderLabels(self.tab4_lable_list)

        # 设置左侧表单的长宽高
        for i in range(0, 10):
            self.tableWidget7.setRowHeight(i, 30)

        for i in range(0, len(self.tab4_lable_list)):
            self.tableWidget7.horizontalHeaderItem(i).setTextAlignment(Qt.AlignHCenter)
            self.tableWidget7.setColumnWidth(i, 300)

        ################## 右布局 #################################
        ## 首先要生成对应的坐标轴类
        temp_list = np.arange(len(self.risk_list))
        ticks = [(i, j) for i, j in zip(temp_list, self.risk_list)]
        strAxis = MyAxisItem(ticks, orientation="bottom")

        # 绘制柱形图所所在位子信息
        self.plotWidget7 = pg.PlotWidget(axisItems={'bottom': strAxis})
        self.plotWidget7.addLegend()
        self.plotWidget7.setFixedHeight(600)
        ## 设置背景色
        self.plotWidget7.setBackground((255, 255, 255))

        #### 测试用 绘图###############################################
        #         # create list of floats
        #         y1 = np.linspace(0, 20, num=20)

        #         # create horizontal list
        #         x1 = np.arange(20)

        #         # create bar chart
        #         bg1 = pg.BarGraphItem(x=x1, height=y1, width=0.6, brush='r')

        #         self.plotWidget7.addItem(bg1)
        ###############################################################

        # 添加控件进入布局
        layout.addWidget(self.tableWidget7)
        layout.addWidget(self.plotWidget7)
        self.tab4.setLayout(layout)

        # 直接启动进程
        self.slotStart_tab4()
        ############################################### tab4 双击事件 ################################################################
        self.tableWidget7.itemDoubleClicked.connect(self.tab4_clicked)

    def tab4_clicked(self, event=None):
        # 获得被点击的对象
        try:
            obj = event
            col_index = self.tab4_lable_list[obj.column()]
            ######################################
            # 测试用
            print(self.Barra_Data[col_index])
            ######################################

            # 当数据完整，即每一个策略对应的 风险数据都有时，开始画图
            if len(self.Barra_Data[col_index]) >= 10:
                # 首先需要按顺序生成 对应的列表
                temp_list = []
                for i in self.risk_list:
                    temp_list.append(self.Barra_Data[col_index][i])
                # create list of floats
                y1 = temp_list[:]

                # create horizontal list
                x1 = np.arange(len(y1))

                # create bar chart
                bg1 = pg.BarGraphItem(x=x1, height=y1, width=0.6, brush=(144, 238, 144), name=col_index + ' Risk')

                self.plotWidget7.clear()
                self.plotWidget7.addItem(bg1)
        except Exception as e:
            print("error in tab4_clicked")
    ####################################################################################################################
    ##############################################################
    #     PyQt5 中的pyQtslot 是python中的decorator，用其可以将一个method 定义为 槽

    #     槽的传参方式 主要是直接传入一个 函数指针

    ##############################################################

    @QtCore.pyqtSlot()
    def slotStart(self):
        # 按钮 暂停使用
        self.pushButton.setEnabled(False)
        # 开启一个新进程用来 更新数据
        self.update_data_thread = UpdateData(self)
        self.update_data_thread.requestChanged.connect(self.onRequestChanged)
        # 线程进入 准备阶段
        self.update_data_thread.start()

    @QtCore.pyqtSlot(int, int, str)
    def onRequestChanged(self, row, msgType, text):
        elems = text.split(',')
        # row =0
        column = 0
        if (msgType == 1):
            myKey = self.RequestRowKey.get(elems[2] + elems[3])
            if (myKey == None):
                myKey = self.g_CurrRequestRow
                self.g_CurrRequestRow += 1
                self.RequestRowKey[elems[2] + elems[3]] = myKey  ### CREATE A REQUEST ROW

            for ele in elems:
                it = self.tableWidget1.item(myKey, column)
                if it is None:
                    it = QtWidgets.QTableWidgetItem()
                    self.tableWidget1.setItem(myKey, column, it)
                if (column == 0):
                    it.setText(AcctNameDict[int(ele)])
                    # print("What is this: %d, and acctName =  %s"%(int(ele),AcctNameDict[int(ele)]))
                elif (column == 4):
                    it.setText(directionType[ele])
                else:
                    it.setText(ele)
                column += 1
            self.tableWidget1.selectRow(myKey)

            myKey = self.BatchRowKey.get(elems[2])
            if (myKey == None):  ### UPDATE ACCT-BATCH TABLE HERE
                myKey = self.g_CurrBatchRow
                self.g_CurrBatchRow += 1
                self.BatchRowKey[elems[2]] = myKey
                self.BatchManagers[elems[2]] = BatchManager()  ### CREATE A BATCH MANAGER
                self.BatchManagers[elems[2]].bookAcctID(int(elems[0]))
            # print("what is the direction code: %s"%(elems[4]))
            myTradeDirection = 1.0 if (int(elems[4]) == 0) else -1.0
            self.BatchManagers[elems[2]].bookTotalValue(elems[3], float(elems[5]) * float(elems[10]) * myTradeDirection)
            self.BatchManagers[elems[2]].bookTradedValue(elems[3], float(elems[8]))  ### need to change here
            # print(elems[3], float(elems[8]))

            ### FILL INFORMATION IN THIS ROW
            ###print("GET NOTIONA:",str(self.BatchManagers[elems[2]].getBuyNotional()),str(self.BatchManagers[elems[2]].getSellNotional()))
            thisAcctID = self.BatchManagers[elems[2]].getAcctID()
            thisAcctIDStr = AcctNameDict[thisAcctID]
            vals1 = self.BatchManagers[elems[2]].getBuyNotional()
            vals2 = self.BatchManagers[elems[2]].getSellNotional()
            vals = [elems[2], thisAcctIDStr, "{:,.2f}".format(vals1[0]), "{:,.2f}".format(vals2[0]),
                    "{:.2%}".format(vals1[1]), "{:.2%}".format(vals2[1])]
            for column in range(0, 6):
                it = self.tableWidget3.item(myKey, column)
                if it is None:
                    it = QtWidgets.QTableWidgetItem()
                    self.tableWidget3.setItem(myKey, column, it)
                it.setText(vals[column])
            self.tableWidget3.selectRow(myKey)

        elif (msgType == 2):
            myKey = self.OrderRowKey.get(elems[0] + elems[1] + elems[12])
            if (myKey == None):
                myKey = self.g_CurrOrderRow
                self.g_CurrOrderRow += 1
                self.OrderRowKey[elems[0] + elems[1] + elems[12]] = myKey
            for ele in elems:
                it = self.tableWidget2.item(myKey, column)
                if it is None:
                    it = QtWidgets.QTableWidgetItem()
                    self.tableWidget2.setItem(myKey, column, it)  # can be done in dictionary of dictionary way, better
                if (column == 3):
                    it.setText(directionType[ele])
                elif (column == 4):
                    it.setText(OpenCloseFlag[ele])
                elif (column == 5):
                    it.setText(hedgeFlag[ele])
                elif (column == 11):
                    it.setText(orderStatus[ele])
                else:
                    it.setText(ele)
                column += 1
            self.tableWidget2.selectRow(myKey)

        elif (msgType == 3):
            myKey = self.ErrorRowKey.get(elems[0] + elems[2])
            if (myKey == None):
                myKey = self.g_CurrErrorRow
                self.g_CurrErrorRow += 1
                self.ErrorRowKey[elems[0] + elems[2]] = myKey
            for ele in elems:
                it = self.tableWidget4.item(myKey, column)
                if it is None:
                    it = QtWidgets.QTableWidgetItem()
                    self.tableWidget4.setItem(myKey, column, it)  # can be done in dictionary of dictionary way, better
                it.setText(ele)
                column += 1
            self.tableWidget4.selectRow(myKey)
        else:
            self.tableWidget1.selectRow(row)

    @QtCore.pyqtSlot()
    def slotStart_tab3(self):
        # 按钮 暂停使用
        self.pushButton3.setEnabled(False)
        # 开启一个新进程用来 更新数据
        self.update_data_thread3 = UpdateData_tab3(self)
        self.update_data_thread3.requestChanged.connect(self.onRequestChanged_tab3)
        # 线程进入 准备阶段
        self.update_data_thread3.start()

    @QtCore.pyqtSlot(int, int, list)
    def onRequestChanged_tab3(self, row, msgType, text):
        # text 即为我们所需要的数据列
        # print(text)

        column = 0

        # message type

        if (msgType == 1):
            strategy_list = self.conf.get('tab3', 'table4_strategies').split(',')
            lable_list = self.conf.get('tab3', 'table4_lables').split(',')
            cat_id = self.g_cat_row_dict.get(text[1])
            if cat_id == None:
                cat_id = self.cat_next_row
                self.cat_next_row += 1
                self.g_cat_row_dict[text[1]] = cat_id
            ## cat_indx 和 cat_name
            for ele in text[1:(len(lable_list) - len(strategy_list)) + 1]:
                it = self.tableWidget4.item(cat_id, column)
                if it is None:
                    it = QtWidgets.QTableWidgetItem()
                    self.tableWidget4.setItem(cat_id, column, it)

                it.setText(ele)
                it.setTextAlignment(Qt.AlignCenter)
                column += 1

            # PNL

            if text[0] in strategy_list:
                col = strategy_list.index(text[0])
                col = len(lable_list) - len(strategy_list) + col
                it = self.tableWidget4.item(cat_id, col)
                if it is None:
                    it = QtWidgets.QTableWidgetItem()
                    self.tableWidget4.setItem(cat_id, col, it)
                it.setText(text[-1])
                it.setTextAlignment(Qt.AlignCenter)
                if float(text[-1]) <= -5:
                    it.setBackground(QtGui.QColor(144, 238, 144))
                if float(text[-1]) >= 5:
                    it.setBackground(QtGui.QColor(193, 210, 240))
        #             if text[0] == 'FLOW':
        #                 it = self.tableWidget4.item(cat_id, 5)
        #                 if it is None:
        #                     it = QtWidgets.QTableWidgetItem()
        #                     self.tableWidget4.setItem(cat_id, 5, it)
        #                 it.setText(text[-1])
        #                 it.setTextAlignment(Qt.AlignCenter)
        #                 if float(text[-1]) <= -5:
        #                     it.setBackground(QtGui.QColor(144, 238, 144))
        #                 if float(text[-1]) >= 5:
        #                     it.setBackground(QtGui.QColor(193, 210, 240))

        #             if text[0] == 'ML':
        #                 it = self.tableWidget4.item(cat_id, 6)
        #                 if it is None:
        #                     it = QtWidgets.QTableWidgetItem()
        #                     self.tableWidget4.setItem(cat_id, 6, it)
        #                 it.setText(text[-1])
        #                 it.setTextAlignment(Qt.AlignCenter)
        #                 if float(text[-1]) <= -5:
        #                     it.setBackground(QtGui.QColor(144, 238, 144))
        #                 if float(text[-1]) >= 5:
        #                     it.setBackground(QtGui.QColor(193, 210, 240))

        #             if text[0] == 'FLML':
        #                 it = self.tableWidget4.item(cat_id, 7)
        #                 if it is None:
        #                     it = QtWidgets.QTableWidgetItem()
        #                     self.tableWidget4.setItem(cat_id, 7, it)
        #                 it.setText(text[-1])
        #                 it.setTextAlignment(Qt.AlignCenter)
        #                 if float(text[-1]) <= -5:
        #                     it.setBackground(QtGui.QColor(144, 238, 144))
        #                 if float(text[-1]) >= 5:
        #                     it.setBackground(QtGui.QColor(193, 210, 240))

        elif (msgType == 2):
            print(text)
            strategy_list = self.conf.get('tab3', 'table5_strategies').split(',')
            lable_list = self.conf.get('tab3', 'table5_lables').split(',')
            winner_id = self.g_winner_row_dict.get(text[1])
            if winner_id == None:
                winner_id = self.winner_next_row
                self.winner_next_row += 1
                self.g_winner_row_dict[text[1]] = winner_id
            ## winner_indx 和 winner_name
            for ele in text[1:(len(lable_list) - len(strategy_list)) + 1]:
                it = self.tableWidget5.item(winner_id, column)
                if it is None:
                    it = QtWidgets.QTableWidgetItem()
                    self.tableWidget5.setItem(winner_id, column, it)

                it.setText(ele)
                it.setTextAlignment(Qt.AlignCenter)
                column += 1

            # PNL

            if text[0] in strategy_list:
                col = strategy_list.index(text[0])
                col = len(lable_list) - len(strategy_list) + col
                it = self.tableWidget5.item(winner_id, col)
                if it is None:
                    it = QtWidgets.QTableWidgetItem()
                    self.tableWidget5.setItem(winner_id, col, it)
                it.setText(text[-2] + ',' + text[-1])
                it.setTextAlignment(Qt.AlignCenter)




        else:
            strategy_list = self.conf.get('tab3', 'table6_strategies').split(',')
            lable_list = self.conf.get('tab3', 'table6_lables').split(',')
            losser_id = self.g_losser_row_dict.get(text[1])
            if losser_id == None:
                losser_id = self.losser_next_row
                self.losser_next_row += 1
                self.g_losser_row_dict[text[1]] = losser_id
            ## losser_indx 和 losser_name
            for ele in text[1:(len(lable_list) - len(strategy_list)) + 1]:
                it = self.tableWidget6.item(losser_id, column)
                if it is None:
                    it = QtWidgets.QTableWidgetItem()
                    self.tableWidget6.setItem(losser_id, column, it)

                it.setText(ele)
                it.setTextAlignment(Qt.AlignCenter)
                column += 1

            # PNL
            strategy_list = self.conf.get('tab3', 'table6_strategies').split(',')
            lable_list = self.conf.get('tab3', 'table6_lables').split(',')
            if text[0] in strategy_list:
                col = strategy_list.index(text[0])
                col = len(lable_list) - len(strategy_list) + col
                it = self.tableWidget6.item(losser_id, col)
                if it is None:
                    it = QtWidgets.QTableWidgetItem()
                    self.tableWidget6.setItem(losser_id, col, it)
                it.setText(text[-2] + ',' + text[-1])
                it.setTextAlignment(Qt.AlignCenter)

    ##############################################tab4 slot#################################################
    @QtCore.pyqtSlot()
    def slotStart_tab4(self):
        # 开启一个新进程用来 更新数据
        self.update_data_thread4 = Update_tab4(self)
        self.update_data_thread4.requestChanged.connect(self.onRequestChanged_tab4)
        # 线程进入 准备阶段
        self.update_data_thread4.start()

    @QtCore.pyqtSlot(tuple)
    def onRequestChanged_tab4(self, text):
        # text 即为我们所需要的数据列
        # print(text)

        lable_list = self.conf.get('tab4', 'table7_lables').split(',')

        # 设置第一列
        for i, element in enumerate(self.risk_list):
            it = QtWidgets.QTableWidgetItem()
            self.tableWidget7.setItem(i, 0, it)
            it.setTextAlignment(Qt.AlignCenter)
            it.setText(element)

        # 根据 传过来的数据设置对应格子

        col_id = self.tab4_lable_list.index(text[1])
        row_id = self.risk_list.index(text[0])
        it = self.tableWidget7.item(row_id, col_id)
        if it is None:
            it = QtWidgets.QTableWidgetItem()
            self.tableWidget7.setItem(row_id, col_id, it)
        self.Barra_Data[text[1]][text[0]] = text[2]
        it.setText(str(text[2]))
        it.setTextAlignment(Qt.AlignCenter)


################################################ main ##############################################################

if __name__ == "__main__":
    # valid_set=get_stock_history_from_csv()
    # valid_tuple_list = []
    # for i in range(len(valid_set)):
    #     valid_tuple_list.append(tuple(valid_set.iloc[i]))

    AcctNameDict = GetAcctName()  # pd.read_csv("./depend/accountMap.txt")
    AcctNameDict[0] = "UNKNOWN"
    print(AcctNameDict.keys())
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    w = Control_sys_Tab()
    w.show()
    sys.exit(app.exec_())

####################################################################################################################