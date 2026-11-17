"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import worker as router_worker
from app.routers import dispatch as router_dispatch
from app.routers import crawljob as router_crawljob
from app.routers import urlfilter as router_urlfilter
from app.routers import dnsresolver as router_dnsresolver
from app.routers import contentextract as router_contentextract
from app.routers import storagestrategy as router_storagestrategy
from app.routers import rendertask as router_rendertask
from app.routers import qualityreport as router_qualityreport
from app.routers import bandwidth as router_bandwidth
from app.routers import retryqueue as router_retryqueue
from app.routers import pagemarker as router_pagemarker
from app.routers import incrementmark as router_incrementmark
from app.routers import configsync as router_configsync
from app.routers import scrapeapi as router_scrapeapi
from app.routers import dataversion as router_dataversion
from app.routers import datasample as router_datasample
from app.routers import alertpolicy as router_alertpolicy

ROUTERS = [router_worker, router_dispatch, router_crawljob, router_urlfilter, router_dnsresolver, router_contentextract, router_storagestrategy, router_rendertask, router_qualityreport, router_bandwidth, router_retryqueue, router_pagemarker, router_incrementmark, router_configsync, router_scrapeapi, router_dataversion, router_datasample, router_alertpolicy]
