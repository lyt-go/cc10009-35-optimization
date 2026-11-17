"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None



class WorkerEntry(BaseModel):
    """工作节点明细结构。"""

    field_0: str | None = None  # 节点编号
    field_1: str | None = None  # 主机地址
    field_2: str | None = None  # 并发槽位数
    field_3: str | None = None  # 地域标签
    field_4: str | None = None  # CPU使用率
    field_5: str | None = None  # 内存可用MB
    field_6: str | None = None  # 上次心跳时间
    field_7: str | None = None  # 节点状态标签

class DispatchEntry(BaseModel):
    """分配策略明细结构。"""

    field_0: str | None = None  # 策略编号
    field_1: str | None = None  # 目标域名
    field_2: str | None = None  # 分配算法
    field_3: str | None = None  # 权重因子
    field_4: str | None = None  # 节点亲和性
    field_5: str | None = None  # 负载阈值
    field_6: str | None = None  # 再平衡间隔
    field_7: str | None = None  # 溢出处理

class CrawljobEntry(BaseModel):
    """作业定义明细结构。"""

    field_0: str | None = None  # 作业编号
    field_1: str | None = None  # 目标站点
    field_2: str | None = None  # 起始URL
    field_3: str | None = None  # 爬取深度
    field_4: str | None = None  # URL去重策略
    field_5: str | None = None  # 页面解析器
    field_6: str | None = None  # 下载超时秒
    field_7: str | None = None  # 最大页面数

class UrlfilterEntry(BaseModel):
    """过滤规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 包含模式
    field_2: str | None = None  # 排除模式
    field_3: str | None = None  # 域名白名单
    field_4: str | None = None  # 路径黑名单
    field_5: str | None = None  # 参数剥离规则
    field_6: str | None = None  # 大小写处理
    field_7: str | None = None  # 尾部斜杠策略

class DnsresolverEntry(BaseModel):
    """解析配置明细结构。"""

    field_0: str | None = None  # 配置编号
    field_1: str | None = None  # 域名模式
    field_2: str | None = None  # DNS服务器
    field_3: str | None = None  # 解析超时毫秒
    field_4: str | None = None  # 缓存TTL秒
    field_5: str | None = None  # A记录策略
    field_6: str | None = None  # IPv6优先
    field_7: str | None = None  # 故障转移地址

class ContentextractEntry(BaseModel):
    """提取器明细结构。"""

    field_0: str | None = None  # 提取器编号
    field_1: str | None = None  # 内容类型
    field_2: str | None = None  # 正文选择器
    field_3: str | None = None  # 时间提取规则
    field_4: str | None = None  # 作者提取规则
    field_5: str | None = None  # 图片下载策略
    field_6: str | None = None  # 结构化标记
    field_7: str | None = None  # 清洗后字数上限

class StoragestrategyEntry(BaseModel):
    """存储方案明细结构。"""

    field_0: str | None = None  # 方案编号
    field_1: str | None = None  # 存储类型
    field_2: str | None = None  # 连接参数
    field_3: str | None = None  # 表名模板
    field_4: str | None = None  # 分区策略
    field_5: str | None = None  # 写入批次大小
    field_6: str | None = None  # 去重字段组合
    field_7: str | None = None  # 过期清理天

class RendertaskEntry(BaseModel):
    """渲染作业明细结构。"""

    field_0: str | None = None  # 作业编号
    field_1: str | None = None  # 目标URL
    field_2: str | None = None  # 浏览器版本
    field_3: str | None = None  # 视口宽度
    field_4: str | None = None  # 视口高度
    field_5: str | None = None  # 等待策略
    field_6: str | None = None  # 脚本注入
    field_7: str | None = None  # 超时阈值秒

class QualityreportEntry(BaseModel):
    """质量报告明细结构。"""

    field_0: str | None = None  # 报告编号
    field_1: str | None = None  # 作业编号
    field_2: str | None = None  # 总URL数
    field_3: str | None = None  # 成功URL数
    field_4: str | None = None  # 失败URL数
    field_5: str | None = None  # 内容完整率
    field_6: str | None = None  # 字段覆盖率
    field_7: str | None = None  # 报告生成时间

class BandwidthEntry(BaseModel):
    """带宽策略明细结构。"""

    field_0: str | None = None  # 策略编号
    field_1: str | None = None  # 节点标识
    field_2: str | None = None  # 下载带宽上限
    field_3: str | None = None  # 上传带宽上限
    field_4: str | None = None  # 突发额度
    field_5: str | None = None  # 限速粒度秒
    field_6: str | None = None  # 优先级权重
    field_7: str | None = None  # 生效时段

class RetryqueueEntry(BaseModel):
    """重试条目明细结构。"""

    field_0: str | None = None  # 条目编号
    field_1: str | None = None  # 失败URL
    field_2: str | None = None  # 失败原因码
    field_3: str | None = None  # 首次失败时间
    field_4: str | None = None  # 已重试次数
    field_5: str | None = None  # 下次重试时间
    field_6: str | None = None  # 退避级别
    field_7: str | None = None  # 最终处置

class PagemarkerEntry(BaseModel):
    """翻页规则明细结构。"""

    field_0: str | None = None  # 规则编号
    field_1: str | None = None  # 目标站点
    field_2: str | None = None  # 翻页类型
    field_3: str | None = None  # 起始页码
    field_4: str | None = None  # 最大页码
    field_5: str | None = None  # 页码参数名
    field_6: str | None = None  # 偏移量参数
    field_7: str | None = None  # 总条数定位器

class IncrementmarkEntry(BaseModel):
    """增量水位明细结构。"""

    field_0: str | None = None  # 水位编号
    field_1: str | None = None  # 目标源
    field_2: str | None = None  # 增量字段名
    field_3: str | None = None  # 当前水位值
    field_4: str | None = None  # 上次采集时间
    field_5: str | None = None  # 增量行数
    field_6: str | None = None  # 延迟分钟
    field_7: str | None = None  # 回退水位

class ConfigsyncEntry(BaseModel):
    """同步任务明细结构。"""

    field_0: str | None = None  # 任务编号
    field_1: str | None = None  # 源节点
    field_2: str | None = None  # 目标节点
    field_3: str | None = None  # 同步类型
    field_4: str | None = None  # 最后同步时间
    field_5: str | None = None  # 配置版本号
    field_6: str | None = None  # 差异摘要
    field_7: str | None = None  # 同步状态

class ScrapeapiEntry(BaseModel):
    """API定义明细结构。"""

    field_0: str | None = None  # API编号
    field_1: str | None = None  # API名称
    field_2: str | None = None  # 请求路径
    field_3: str | None = None  # 数据源绑定
    field_4: str | None = None  # 参数模板
    field_5: str | None = None  # 缓存策略
    field_6: str | None = None  # 速率限制
    field_7: str | None = None  # 返回格式

class DataversionEntry(BaseModel):
    """数据版本明细结构。"""

    field_0: str | None = None  # 版本编号
    field_1: str | None = None  # 数据源标识
    field_2: str | None = None  # 当前代际
    field_3: str | None = None  # 依赖版本
    field_4: str | None = None  # 部署环境
    field_5: str | None = None  # 数据库连接
    field_6: str | None = None  # 兼容状态
    field_7: str | None = None  # 清单条目数

class DatasampleEntry(BaseModel):
    """抽样方案明细结构。"""

    field_0: str | None = None  # 方案编号
    field_1: str | None = None  # 数据源
    field_2: str | None = None  # 抽样方式
    field_3: str | None = None  # 抽样比例
    field_4: str | None = None  # 最小样本量
    field_5: str | None = None  # 分层字段
    field_6: str | None = None  # 抽样周期
    field_7: str | None = None  # 输出路径

class AlertpolicyEntry(BaseModel):
    """告警策略明细结构。"""

    field_0: str | None = None  # 策略编号
    field_1: str | None = None  # 监控指标
    field_2: str | None = None  # 触发条件
    field_3: str | None = None  # 告警级别
    field_4: str | None = None  # 静默时长
    field_5: str | None = None  # 通知渠道
    field_6: str | None = None  # 升级规则
    field_7: str | None = None  # 修复建议链接
