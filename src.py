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

        ### 画k线图 ##########

        # 设置画pen 颜色，用来画线
        # 颜色代码使用 RGB值，缩写，都可以
        #         p1.setPen(pg.mkPen((0,0,0)))
        #         for i in range(len(self.data)):
        #             #画一条最大值最小值之间的线
        #             p1.drawLine(QPointF(i,self.data[i][3]),QPointF(i,self.data[i][2]))
        #             # 设置画刷颜色
        #             if self.data[i][1]>self.data[i][4]:
        #                 p1.setBrush(pg.mkBrush('g'))
        #             else:
        #                 p1.setBrush(pg.mkBrush('r'))
        #             p1.drawRect(QRectF(i-0.3,self.data[i][1],0.6,self.data[i][4]-self.data[i][1]))

        #### 画自定义的线 ####################

        ## close 线
        p1.setPen(pg.mkPen(0, 0, 255))
        for i in range(len(self.data) - 1):
            p1.drawLine(QPointF(i, self.data[i][4]), QPointF(i + 1, self.data[i + 1][4]))

        ## low 线
        p1.setPen(pg.mkPen(0, 255, 0))
        for i in range(len(self.data) - 1):
            p1.drawLine(QPointF(i, self.data[i][3]), QPointF(i + 1, self.data[i + 1][3]))

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


#### tab2 线程############################
class Update_tab2(QtCore.QThread):
    requestChange = QtCore.pyqtSignal(tuple)

    def __init__(self, parent=None):
        super(Update_tab2, self).__init__(parent)
        # 设置工作状态与初始num数值

    def __del__(self):
        # 线程状态改变与线程终止
        self.working = False
        self.wait()

    def run(self):
        #         context = zmq.Context()
        #         sock = context.socket(zmq.SUB)
        #         sock.setsockopt(zmq.SUBSCRIBE, b"FLOW")
        #         sock.setsockopt(zmq.HEARTBEAT_IVL,     5000)
        #         sock.setsockopt(zmq.HEARTBEAT_TIMEOUT, 3000)

        #         sock.connect("tcp://192.168.0.32:19006")
        while True:
            #             sss=sock.recv()
            #             msg = sss.decode("ascii").split(",")
            #             new_data=[]
            #             new_data.append(msg[1])#time
            #             new_data.append(float(msg[2]))#open
            #             new_data.append(float(msg[3])*1.01)#high
            #             new_data.append(float(msg[4])*0.99)#low
            #             new_data.append(float(msg[5]))#close
            new_data = get_stock_info()
            #             for i in msg[2:]:
            #                 new_data.append(float(i))

            # 如果一直无信息发送过来，则等待
            if new_data is None:
                # print("waiting for new msg")
                time.sleep(1)
                continue
            else:
                # 通过自定义信号把待显示的字符串传递给槽函数
                print(tuple(new_data))
                self.requestChange.emit(tuple(new_data))


## 主基类，是 整个GUI的主窗口，内部含有三个子窗口
class Control_sys_Tab(QTabWidget):
    def __init__(self, parent=None):
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
        super().__init__(parent)

        self.setObjectName("Control_system")
        self.resize(1800, 985)
        self.setWindowTitle("实时监控系统")

        # 创建3个选项卡小控件窗口
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        self.tab3 = QWidget()

        # 将三个选项卡添加到顶层窗口中
        self.addTab(self.tab1, "交易界面")
        self.addTab(self.tab2, "损益界面")
        self.addTab(self.tab3, "风险分析")

        # 记录tab2 中的数据，后续会从其他类中读取数据，并更新和作图
        self.Data = []
        self.work = Update_tab2()
        self.label = pg.TextItem()

        # 每个选项卡自定义的内容
        self.tab1UI()
        self.tab2UI()
        self.tab3UI()

        self.pushButton.clicked.connect(self.slotStart)

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
    ######################################

    ### 测试线程用代码
    def execute(self):
        # 启动线程
        self.work.start()
        # 线程自定义信号连接的槽函数
        self.work.requestChange.connect(self.display)

    def display(self, new_data):
        # 由于自定义信号时自动传递0个字符串参数，所以在这个槽函数中要接受0个参数
        # print(new_data)
        self.plotData(new_data)

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

                    #                     print(pos)
                    mousePoint = self.plt.plotItem.vb.mapSceneToView(pos)  # 转换鼠标坐标
                    index = int(mousePoint.x())  # 鼠标所处的X轴坐标
                    pos_y = int(mousePoint.y())  # 鼠标所处的Y轴坐标
                    if -1 < index < len(self.Data):
                        # 在label中写入HTML
                        self.label.setHtml(
                            "<p style='color:black'><strong>时间：{0}</strong></p><p style='color:black'>\
                            开盘：{1}</p><p style='color:black'>\
                            收盘：{2}</p><p style='color:black'>\
                            最高价：<span style='color:red;'>{3}</span></p><p style='color:black'>\
                            最低价：<span style='color:green;'>{4}</span></p>".format(
                                self.Data[index][0], self.Data[index][1], self.Data[index][4],
                                self.Data[index][2], self.Data[index][3]))
                        self.label.setPos(mousePoint.x(), mousePoint.y())  # 设置label的位置
                        # print(self.label)

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
            self.Data.append(temp)

    def plotData(self, new_data):
        # print(len(self.Data))
        if new_data != None:
            item = DrawRecItem(self.Data)

            ## 清空layout2 以重新插入图片
            for i in range(self.layout2.count()):
                self.layout2.itemAt(i).widget().deleteLater()

            index = range(len(self.Data))
            time_list = []
            for i in index:
                temp = self.Data[i][0]
                time_list.append(temp)
            ticks = [(i, j) for i, j in zip(index, time_list)]
            strAxis = MyAxisItem(ticks, orientation="bottom")

            self.plt = pg.PlotWidget(axisItems={'bottom': strAxis})
            self.plt2 = pg.PlotWidget()

            ## 设置背景颜色
            self.plt.setBackground((255, 255, 255))

            # 将iTem加入到plotwidget控件中
            self.plt.addItem(item)

            # 将控件添加到pyqt中
            self.layout2.addWidget(self.plt, 0, 0)

            # 控件2
            self.layout2.addWidget(self.plt2, 0, 1)

            # 将layout 布局添加到 tab2中
            self.tab2.setLayout(self.layout2)
            self.Data.append(new_data)

            self.vLine = pg.InfiniteLine(angle=90, movable=False, )  # 创建一个垂直线条
            self.hLine = pg.InfiniteLine(angle=0, movable=False, )  # 创建一个水平线条
            self.plt.addItem(self.vLine, ignoreBounds=True)  # 在图形部件中添加垂直线条
            self.plt.addItem(self.hLine, ignoreBounds=True)  # 在图形部件中添加水平线条
            self.move_slot = pg.SignalProxy(self.plt.scene().sigMouseMoved, rateLimit=60, slot=self.print_slot)

    def tab2UI(self):
        #         self.timer_start()
        self.layout2 = QGridLayout()
        # self.timer_start()
        self.execute()

    def tab3UI(self):

        return

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
            print(elems[3], float(elems[8]))

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