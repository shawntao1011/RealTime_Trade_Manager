import sys
import time
import zmq
from datetime import datetime
import pandas as pd
import numpy as np
from PyQt5 import sip
from PyQt5.QtWidgets import *
from PyQt5 import QtWidgets,QtCore, QtGui
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import *
from PyQt5.QtGui import QPicture,QPainter
from PyQt5.QtCore import QPointF,QRectF
import pyqtgraph as pg


##################### global Variable##############################

AcctNameDict = {}

priceType ={}
priceType['1'] = "AnyPrice"
priceType['2'] = "LimitPrice"
priceType['u'] = "Unknown"
priceType

directionType ={}
directionType['0'] = "Buy"
directionType['1'] = "Sell"
directionType['u'] = "Unknown"
directionType

OpenCloseFlag ={}
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

orderStatus ={}
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
    hdata_reindexed=hdata.reset_index()
    valid_set = hdata_reindexed.sort_values(by='Date').reset_index(drop=True)
    return valid_set

## 从本地下载数据
def get_stock_history_from_csv(path="nflx.csv"):
    temp=pd.read_csv(path,index_col=0)
    valid_set=temp.sort_values(by='Date').reset_index(drop=True)
    return valid_set

## 模拟数据流，逐条获取数据
def get_stock_info():
    global valid_tuple_list
    if len(valid_tuple_list)>0:
        temp=valid_tuple_list[0]
        valid_tuple_list=valid_tuple_list[1:]
        return temp

#########################################################################################################

################################### Self-design classes #################################################
## Batch Manager 类，负责管理batch
class BatchManager():

    def __init__(self):
        self.BuyValuePerRQID = {}
        self.SellValuePerRQID = {}
        self.BuyTotalValuePerRQID = {}
        self.SellTotalValuePerRQID = {}
        self.AcctID = 0
    def bookAcctID(self,acct):
        self.AcctID = acct

    def bookTradedValue(self,RQID,value):
        if(value > 0):
            self.BuyValuePerRQID[RQID] = value
            #print("BUY: %f"%(self.BuyValuePerRQID[RQID]))
        else:
            self.SellValuePerRQID[RQID] = value
            #print("SELL: %f"%(self.SellValuePerRQID[RQID]))
    def bookTotalValue(self,RQID,value):
        if(value > 0):
            self.BuyTotalValuePerRQID[RQID] = value
            #print("BUY: %f"%(self.BuyValuePerRQID[RQID]))
        else:
            self.SellTotalValuePerRQID[RQID] = value
            #print("SELL: %f"%(self.SellValuePerRQID[RQID]))

    def getBuyNotional(self):
        #print("BUY NOTIONAL : ",self.BuyValuePerRQID.values(),sum(self.BuyValuePerRQID.values()))
        boughtNotional = sum(self.BuyValuePerRQID.values())
        totalBuyNotional  = sum(self.BuyTotalValuePerRQID.values())
        myFillRate     = (boughtNotional / totalBuyNotional) if (totalBuyNotional > 0) else 0
        return [boughtNotional,myFillRate,totalBuyNotional]

    def getSellNotional(self):
        #print("SELL NOTIONAL : ",self.SellValuePerRQID.values(),sum(self.SellValuePerRQID.values()))
        soldNoitional = sum(self.SellValuePerRQID.values())
        totalSellNotional = sum(self.SellTotalValuePerRQID.values())
        myFillRate    = soldNoitional / totalSellNotional if((abs(totalSellNotional)) > 0) else 0
        return [soldNoitional,myFillRate,totalSellNotional]

    def getAcctID(self):
        return self.AcctID;

## updateData 类 继承于 qthread 负责实时更新数据
class UpdateData(QtCore.QThread):
    requestChanged = QtCore.pyqtSignal(int, int, str)  # rowIndex, msgType,msg

    def run(self):
        requestChanged = QtCore.pyqtSignal(int, int, str)
        context = zmq.Context()
        sock = context.socket(zmq.SUB)
        sock.setsockopt(zmq.SUBSCRIBE, b"EMS_GUI_SubOda")
        sock.setsockopt(zmq.SUBSCRIBE, b"EMS_GUI_Request")
        sock.setsockopt(zmq.SUBSCRIBE, b"EMS_GUI_Error")
        sock.setsockopt(zmq.HEARTBEAT_IVL,     5000)
        sock.setsockopt(zmq.HEARTBEAT_TIMEOUT, 3000)
        #print("hello")
        sock.connect("tcp://192.168.0.66:15300")
        sock.connect("tcp://117.185.37.175:51336")
		### DOUBLE RQID Problem

        while True:
            msg = sock.recv()
            msgs = msg.decode("ascii").split("|")
            #msgs= msg.split(',')
            #self.dataChanged.emit(2, 2, msgs[0])
            print(msgs[0],msgs[1])
            if(msgs[0] == "EMS_GUI_Request"):
                self.requestChanged.emit(1,1, msgs[1])
                print(msgs[1])
            elif(msgs[0] == "EMS_GUI_SubOda"):
                self.requestChanged.emit(2,2, msgs[1])
                print(msgs[1])
            elif(msgs[0] == "EMS_GUI_Error"):
                self.requestChanged.emit(2,3, msgs[1])
                print(msgs[1])

## 绘制图形用的 class 该类目前生成了k线图
class DrawRecItem(pg.GraphicsObject):
    def __init__(self, data):
        super().__init__()
        self.data = data
        self.draw_rect()

    def draw_rect(self):

        self.picture = QPicture()
        p1 = QPainter(self.picture)

        # 设置画pen 颜色，用来画线
        p1.setPen(pg.mkPen('w'))
        for i in range(len(self.data)):
            # 画一条最大值最小值之间的线
            p1.drawLine(QPointF(i, self.data[i][3]), QPointF(i, self.data[i][2]))
            # 设置画刷颜色
            if self.data[i][1] > self.data[i][4]:
                p1.setBrush(pg.mkBrush('g'))
            else:
                p1.setBrush(pg.mkBrush('r'))
            p1.drawRect(QRectF(i - 0.3, self.data[i][1], 0.6, self.data[i][4] - self.data[i][1]))

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
                vstr=self.x_strings[np.abs(self.x_values-vs).argmin()]
            else:
                vstr = ''

            strings.append(vstr)
        return strings

## 主基类，是 整个GUI的主窗口，内部含有三个子窗口
class Control_sys_Tab(QTabWidget):
    def __init__(self, parent=None):
        #         self.RequestRowKey ={}
        #         self.OrderRowKey  ={}
        #         self.BatchRowKey  ={}   #To manage batch row index
        #         self.ErrorRowKey  ={}   #To manage error row index
        #         self.BuyBatchValue = {}
        #         self.SellBatchValue= {}
        #         self.BatchManagers  ={} # To manage value for each batch
        #         self.g_CurrRequestRow = 0
        #         self.g_CurrOrderRow  = 0
        #         self.g_CurrBatchRow  = 0
        #         self.g_CurrErrorRow  = 0
        super().__init__(parent)

        self.setObjectName("Control_system")
        self.resize(1800, 985)
        self.setWindowTitle("实时监控系统")

        # 记录tab2 中的数据，后续会从其他类中读取数据，并更新和作图
        self.Data = []

        # 创建3个选项卡小控件窗口
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        self.tab3 = QWidget()

        # 将三个选项卡添加到顶层窗口中
        self.addTab(self.tab1, "交易界面")
        self.addTab(self.tab2, "PNL展示界面")
        self.addTab(self.tab3, "PNL定时发送")

        # 每个选项卡自定义的内容
        self.tab1UI()
        self.tab2UI()
        self.tab3UI()

    ################tab1#################################

    def tab1UI(self):
        # 设置主布局
        layout = QHBoxLayout()

        sec_layout = QFormLayout()

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
    # 定义一个计时器
    def timer_start(self):
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.plotData)
        self.timer.start(1000)

    def append_stock_data(self):
        temp = get_stock_info()
        if temp != None:
            self.Data.append(temp)

    def plotData(self):
        # print(len(self.Data))
        self.layout = QVBoxLayout()
        item = DrawRecItem(self.Data)

        index = range(len(self.Data))
        time_list = []
        for i in index:
            temp = self.Data[i][0]
            time_list.append(temp)
        ticks = [(i, j) for i, j in zip(index, time_list)]
        strAxis = MyAxisItem(ticks, orientation="bottom")

        plt = pg.PlotWidget(axisItems={'bottom': strAxis})

        # 将iTem加入到plotwidget控件中
        plt.addItem(item)

        # 将控件添加到pyqt中
        self.layout.addWidget(plt)
        # 将layout 布局添加到 tab2中
        self.tab2.setLayout(self.layout)
        self.append_stock_data()
        self.layout.deleteLater()

    def tab2UI(self):
        #         self.timer_start()
        self.timer_start()

    def tab3UI(self):

        return

    ####################################################################################################################


################################################ main ##############################################################

if __name__ == "__main__":
    valid_set=get_stock_history_from_csv()
    valid_tuple_list = []
    for i in range(len(valid_set)):
        valid_tuple_list.append(tuple(valid_set.iloc[i]))

    AcctNameDict = GetAcctName()#pd.read_csv("./depend/accountMap.txt")
    AcctNameDict[0] = "UNKNOWN"
    print(AcctNameDict.keys())
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    w = Control_sys_Tab()
    w.show()
    sys.exit(app.exec_())


####################################################################################################################