"""外部渠道（channels）—— 让 WorkBuddy 助手能从桌面 App 之外被触达。

当前只有 Telegram（WB-072）：一个后台长轮询桥接，把 Telegram 收到的消息接入真实
agent 工具循环，再把回复发回。企业微信/WhatsApp 等待渠道凭证具备后再加同构实现。
"""
