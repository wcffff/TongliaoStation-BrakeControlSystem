# Tongliao Station Brake Control System
通辽站铁路停车器控制系统，包括上位机（控制系统），下位机（防溜器）以及与SAM的接口。

***

## 停车器与SAM及下位机硬件结构图

停车器控制系统又如下模块组成：
* 下位机（1路防溜器和3路停车器）
* 下位机的CAN模块<span style="color: red;">（需要配置）</span>
* CAN转485通信模块<span style="color: red;">（需要配置）</span>
* 串口服务器<span style="color: red;">（需要配置）</span>
* 交换机（用于TCP通信，获取IP）
* NAS（共享存储）
* 上位机（停车器控制系统软件）
* SAM（铁科院自动控制系统）

具体接线见下图：
![本地图片](./pictures/控制系统.png)

需要配置的模块：
* 串口服务器见智嵌物联官网（配一下485和232的波特率以及端口号），见链接:[串口服务器](https://www.zhiqwl.com/list_146/401.html)
* CAN模块及CAN转485（配置CAN和485的波特率，CAN模块需要配置ID号，同一CAN网络下的ID号不能相同）。见链接：[CAN转485](https://www.zhiqwl.com/list_130/192.html)，[CAN模块](https://www.zhiqwl.com/list_130/190.html)
* <span style="color: red;">注：</span>485串口波特率设置为115200，CAN模块波特率100k，SAM的232串口波特率为9600

