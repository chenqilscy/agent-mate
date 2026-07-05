import { Composer } from '../components/composer/Composer'
import { CatLogo, IcSearch, IcShare, IcHistory, IcPanel, IcGear } from '../lib/icons'
import { toast } from '../stores/toastStore'

// Assistant (external-channel) view. Content is the prototype's canned intro; the
// real external-channel connectivity (企业微信/WhatsApp/邮件) is P2 (M5+). The
// composer is present and consistent, routing to a toast until channels land.
export function AssistantView() {
  return (
    <section className="view active split" data-view="assistant">
      <div className="chat-col">
        <div className="chat-head">
          <div className="ast-conn">
            已连接：<span className="ac-chip">🟢 微信小程序</span>
            <IcGear onClick={() => toast('助理设置')} />
          </div>
          <div className="ch-r" style={{ marginLeft: 'auto' }}>
            <div className="fic" aria-label="搜索" onClick={() => toast('对话内搜索')}><IcSearch /></div>
            <div className="fic" aria-label="分享" onClick={() => toast('分享对话')}><IcShare /></div>
            <div className="fic" aria-label="历史提问" onClick={() => toast('历史提问')}><IcHistory /></div>
            <div className="fic" aria-label="产物面板" onClick={() => toast('产物面板')}><IcPanel /></div>
          </div>
        </div>

        <div className="chat-scroll">
          <div className="msg bot">
            <CatLogo className="bot-ic" />
            <div className="bot-body">
              <p>看来这是我们的第一次正式交流。在深入之前，我想先跟你一起定下来一些基本的东西，这样以后合作起来会更顺畅。</p>
              <p>关于我这边的事比较简单——我目前还没有名字、没有固定风格，这些你可以帮我定。你呢？怎么称呼你比较合适？平时做些什么，有什么特别在忙的项目吗？</p>
            </div>
          </div>
          <div className="msg me"><div className="bub-me">给助理发一条消息，告诉他我们连通了</div></div>
          <div className="msg bot">
            <CatLogo className="bot-ic" />
            <div className="bot-body">
              <div className="bot-nm">WorkBuddy</div>
              <div className="bot-st">已完成 ›</div>
              <p>好的！你指的"助理"是通过什么方式发消息呢？比如：</p>
              <ul>
                <li><b>企业微信 / 钉钉 / 飞书</b> — 如果有连通的账号</li>
                <li><b>WhatsApp</b> — 我可以帮忙连接你的个人 WhatsApp</li>
                <li><b>邮件</b> — 通过 Gmail 等</li>
                <li><b>其他方式</b> — 你来说，我来想办法</li>
              </ul>
              <p>另外，方便告诉我这位助理怎么称呼吗？这样消息写得更自然 😊</p>
            </div>
          </div>
        </div>

        <div className="chat-foot">
          <Composer variant="chat" onSend={() => toast('助理外部渠道连通功能将在 M5 落地')} />
          <div className="disc">内容由 AI 生成，请核实重要信息</div>
        </div>
      </div>
    </section>
  )
}
