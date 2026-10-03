window.MYALPHA_RESEARCH_METHODS = {
  version: '5.1.1',
  updated_at: '2026-09-28',
  principle: '专业指标保留，但默认先给普通投资者一句话结论、原因、可执行方案和失效条件。博主方法只作为研究来源，不自动变成交易规则；作者明确披露的股票/期权价格、执行价、到期日、仓位或退出条件会单独记录为历史操作实例，供复盘参考。',
  authors: [{id:'brightline', name:'BrightLine'}],
  methods: [
    {
      id:'index-first', author:'BrightLine', category:'资产配置', name:'没有可证明的优势时，指数优先',
      plain:'如果你不能清楚说明自己为什么比市场更有优势，就不要把主要资金押在个股判断上。',
      action:'把宽基/成长指数作为底盘；个股只放在“我愿意持续研究并能说明风险”的卫星层。',
      invalid:'当你确实建立了可重复验证的研究优势时，才讨论提高个股权重；不能因为几次赚钱就认定自己有优势。',
      metrics:[
        {name:'Edge（研究优势）', simple:'你是否拥有市场没有的更好信息、分析、行为纪律或持有周期优势。', read:'无法具体写出来 = 默认按“没有优势”处理。'},
        {name:'相对基准收益', simple:'个股/方法是否长期跑赢一个合理基准，例如 QQQM，而不是只看赚没赚钱。', read:'至少看一段完整周期；少数成功案例不够。'}
      ],
      site:'核心ETF继续独立管理；个股研究卡新增“我的优势是什么 / 为什么不是直接买指数”。',
      sources:['https://blog.wenxuecity.com/myblog/82458/202605/10455.html']
    },
    {
      id:'thesis-first', author:'BrightLine', category:'个股研究', name:'先写 Thesis，再谈买入',
      plain:'买个股前先写“为什么可能赚钱、什么事实说明我错了”，而不是买了以后再找理由。',
      action:'个股至少写四项：投资论点、催化剂、最大风险、失效条件；没有失效条件就先放观察池。',
      invalid:'如果核心假设被事实推翻，即使股价暂时没有大跌，也要重新评估。',
      metrics:[
        {name:'催化剂', simple:'可能让市场重新认识公司的具体事件，例如订单、产品、利润改善。', read:'越具体越好；“未来会很好”不算催化剂。'},
        {name:'失效条件', simple:'出现什么事实后，原来的逻辑就不成立。', read:'必须是可观察事件，而不是“跌太多了”。'}
      ],
      site:'个股详情页固定加入 Thesis / 催化剂 / 反证 / 下一核验日期。',
      sources:['https://blog.wenxuecity.com/myblog/82458/202511/655.html','https://blog.wenxuecity.com/myblog/82458/202605/10455.html']
    },
    {
      id:'survival-first', author:'BrightLine', category:'风险管理', name:'Survival > Timing：先保证摔不死',
      plain:'不要把策略建立在“我能逃顶”上，而要保证即使判断错、遇到大回撤，也还有继续投资的能力。',
      action:'不因害怕大跌把长期核心仓全部清空；同时控制杠杆、单一高风险仓位和事件暴露。',
      invalid:'如果组合一次常见的大回撤就会迫使你卖出或补保证金，说明风险结构需要先调整。',
      metrics:[
        {name:'最大回撤', simple:'从阶段高点跌到低点最多跌了多少。', read:'它回答“最难受时会有多难受”，不是预测未来。'},
        {name:'杠杆敞口', simple:'市场每波动 1%，你的组合大约会被放大多少。', read:'杠杆越高，错误判断越难熬。'},
        {name:'事件风险', simple:'财报、FDA、诉讼、政策等可能造成跳空的事件。', read:'事件临近时，普通止损不一定按预期价格成交。'}
      ],
      site:'加入“生存检查”：杠杆 / 跳空事件 / 失效条件 / 集中度是否清楚；不显示真实账户金额。',
      sources:['https://blog.wenxuecity.com/myblog/82458/202605/18645.html','https://blog.wenxuecity.com/myblog/82458/202606/4319.html']
    },
    {
      id:'stay-invested', author:'BrightLine', category:'长期纪律', name:'Time in the Market：长期趋势里不要过度折腾',
      plain:'长期大趋势里，频繁猜顶部和底部很容易把自己甩下车；核心仓的任务是持续在场。',
      action:'核心ETF维持既定纪律；回撤时按预设档位而不是情绪决定。个股交易仍需单独规则。',
      invalid:'当长期逻辑或资产定位改变时再调整；不能把“长期在场”套到所有高风险个股和短期期权。',
      metrics:[
        {name:'长期趋势', simple:'价格是否仍处在较长期的上升结构中。', read:'它是背景，不是精确买点。'},
        {name:'回撤档位', simple:'从历史高点回落到预先设定的区间。', read:'用于纪律化分批，而不是预测最低点。'}
      ],
      site:'保留核心ETF回撤档位与Trend Pulse分工：一个管长期纪律，一个做趋势背景。',
      sources:['https://blog.wenxuecity.com/myblog/82458/202604/16240.html','https://blog.wenxuecity.com/myblog/82458/202606/']
    },
    {
      id:'probability', author:'BrightLine', category:'决策框架', name:'把仓位当成概率题，不追求每次猜对',
      plain:'投资不是考试，不需要每次都对；更重要的是赚的时候能覆盖亏的时候，而且一次错误不会伤筋动骨。',
      action:'每种方法记录胜率、平均盈利、平均亏损、最大回撤和样本数；样本太少时只写“待验证”。',
      invalid:'如果一套方法只能靠极少数幸运案例成立，或回撤大到无法执行，就不能把它当稳定策略。',
      metrics:[
        {name:'胜率', simple:'10次里大约有几次赚钱。', read:'胜率高不一定好，关键还要看赚多少、亏多少。'},
        {name:'盈亏比', simple:'平均赚 2 元、平均亏 1 元，盈亏比约 2:1。', read:'胜率和盈亏比必须一起看。'},
        {name:'期望值', simple:'把胜率和盈亏比合起来看长期平均结果。', read:'正期望也可能连续亏很多次，所以还要看回撤。'}
      ],
      site:'方法验证统一显示样本数、胜率、盈亏比、最大回撤、相对QQQM，不做100分制评分。',
      sources:['https://blog.wenxuecity.com/myblog/82458/202606/']
    },
    {
      id:'calculated-risk', author:'BrightLine', category:'仓位管理', name:'风险不是不要承担，而是要能算清楚',
      plain:'高收益通常伴随高风险；普通投资者真正需要的是“最坏结果我能不能承受”，而不是只看最好结果。',
      action:'高风险机会放在卫星层；核心资产和高波动工具分开管理，不复制别人的仓位比例。',
      invalid:'当你说不清最大可能损失、资金占用和失败后还能不能继续执行时，不应继续加复杂度。',
      metrics:[
        {name:'最大损失', simple:'最坏情况下可能亏多少，期权尤其要先看这一项。', read:'先看损失，再看收益。'},
        {name:'集中度', simple:'单一股票/主题占组合的比重。', read:'越集中，单一判断错误影响越大。'}
      ],
      site:'期权和高波动资产增加“最坏结果 / 资金占用 / 事件风险”普通话解释。',
      sources:['https://blog.wenxuecity.com/myblog/82458/202605/4789.html']
    },
    {
      id:'options-tool', author:'BrightLine', category:'期权', name:'期权是表达工具，不是研究替代品',
      plain:'先有观点，再决定是否用期权。期权可以放大收益，也会放大“时间不够、波动率下降、方向错”的代价。',
      action:'建仓前回答：为什么不用股票、需要多长时间、最大损失是多少、什么事件必须在到期前发生。',
      invalid:'如果唯一理由只是“便宜、能赚得更多”，但没有时间和风险逻辑，就不适合用期权。',
      metrics:[
        {name:'DTE（剩余天数）', simple:'距离期权到期还有多少天。', read:'时间越短，对方向和时点要求越高。'},
        {name:'IV（隐含波动率）', simple:'市场给这张期权定的“未来波动预期”。', read:'IV很高时，期权可能很贵；方向看对也可能因IV下降而少赚。'},
        {name:'Theta', simple:'时间过去一天，期权价值可能自然损失多少。', read:'对买方通常是成本；短期期权更敏感。'},
        {name:'Delta', simple:'股价每变动1元，期权价格大约跟着变多少。', read:'它是近似敏感度，不是胜率。'}
      ],
      site:'期权模块默认先显示“为什么用期权 / 到期逻辑 / 最大风险”，Greeks放展开层。',
      sources:['https://blog.wenxuecity.com/myblog/82458/202605/','https://blog.wenxuecity.com/myblog/82458/202605/8868.html']
    },
    {
      id:'hedge', author:'BrightLine', category:'对冲', name:'对冲的目的首先是让自己能继续执行',
      plain:'保险不是为了每次都赚钱，而是为了极端下跌时少受伤、少被迫卖出。',
      action:'只有当持仓与QQQ等基准高度相关时，才讨论指数Put是否能起到组合保险作用；先算成本和保护范围。',
      invalid:'对冲成本长期过高、与持仓相关性太低，或买完保险反而加大风险仓位，都可能失去意义。',
      metrics:[
        {name:'相关性', simple:'你的持仓和QQQ是否经常一起涨跌。', read:'相关性越高，用QQQ对冲才越“对症”。'},
        {name:'保护成本', simple:'每年为了保险付出的权利金。', read:'保险太贵会长期拖累收益。'},
        {name:'VIX / IV', simple:'市场恐慌和期权价格的大致温度。', read:'通常波动率越高，买Put越贵；不能只看一个数。'}
      ],
      site:'对冲模块给普通投资者先显示“保护什么 / 花多少钱 / 什么时候有效”，再展开Greeks。',
      sources:['https://blog.wenxuecity.com/myblog/82458/202605/8868.html']
    },
    {
      id:'fomo-luck', author:'BrightLine', category:'行为纪律', name:'别把牛市和运气误认为能力',
      plain:'赚得多的时候最容易提高仓位、追热点、缩短期限；恰恰这时要检查自己靠的是方法还是行情。',
      action:'每次盈利复盘“如果市场环境不同，这套方法还成立吗”；同时保存失败案例，不只看成功截图。',
      invalid:'如果方法只在单一强牛市有效，或解释总是在结果出来以后改变，就不能叫稳定优势。',
      metrics:[
        {name:'相对基准', simple:'你的收益比QQQM等基准多了多少。', read:'市场整体大涨时，绝对赚钱不等于有额外能力。'},
        {name:'最大不利波动', simple:'持有过程中最差一度亏了多少。', read:'用于判断方法是否真的能拿得住。'}
      ],
      site:'复盘页同时显示“市场基准、最大不利波动、最终结果”，避免只看收益率。',
      sources:['https://blog.wenxuecity.com/myblog/82458/202605/','https://blog.wenxuecity.com/myblog/82458/202606/4319.html']
    },
    {
      id:'ai-assistant', author:'BrightLine', category:'研究工具', name:'AI要连接真实数据，并把事实和推理分开',
      plain:'AI很适合做筛选、归纳、计算和检查，但它不能把没有的数据“想出来”。',
      action:'行情、财报、事件先接真实数据源；AI负责解释和对照规则；关键结论保留来源与更新时间。',
      invalid:'如果数据源过期、缺失，或AI结论无法追溯到数据，就只显示“证据不足”，不输出确定判断。',
      metrics:[
        {name:'数据更新时间', simple:'这组行情/财报是什么时候更新的。', read:'时间不清楚，结论可信度要下降。'},
        {name:'数据完整性', simple:'关键字段有没有缺失或异常。', read:'异常数据先停止推理，不用“聪明算法”补猜。'}
      ],
      site:'继续强化数据状态中心；所有AI解释旁边显示来源、日期、是否完整。',
      sources:['https://blog.wenxuecity.com/myblog/82458/202606/12430.html']
    },
    {
      id:'trend-confirm', author:'BrightLine', category:'技术确认', name:'趋势指标只做确认，不替代基本面',
      plain:'技术指标可以帮助判断“现在强不强、有没有转弱”，但不能告诉你公司值多少钱。',
      action:'个股先有研究论点，再用Trend Pulse、动能、均线等做第二层确认；不要把单一指标当买卖按钮。',
      invalid:'基本面逻辑被破坏时，即使技术图形还好看，也要重新评估；反过来核心ETF也不因短期指标转弱就机械清仓。',
      metrics:[
        {name:'Trend Pulse', simple:'把趋势、动能和结构合成一个 -100 到 +100 的背景分数。', read:'+50以上表示趋势较强，不等于“现在必须买”。'},
        {name:'5日动能', simple:'最近几天趋势是在加速还是减速。', read:'改善=短期变强；转负=需要留意，但不是单独卖出信号。'},
        {name:'200日均线', simple:'长期平均成本的大致参考。', read:'价格在其上方通常代表长期结构较强，但仍要看估值和基本面。'}
      ],
      site:'全站默认先显示“趋势偏强/偏弱 + 怎么理解”，专业指标收在展开层。',
      sources:['https://blog.wenxuecity.com/myblog/82458/202511/6299.html','https://blog.wenxuecity.com/myblog/82458/202604/16240.html']
    },
    {
      id:'great-company-price', author:'BrightLine', category:'估值', name:'好公司不等于任何价格都值得买',
      plain:'公司质量和买入价格是两件事。再优秀的公司，如果市场已经把完美未来全算进去了，风险也可能很高。',
      action:'研究高成长公司时至少做“基准情景 / 乐观情景 / 悲观情景”，不要只用最好情况支持当前价格。',
      invalid:'关键增长假设、利润率或市场份额无法兑现时，估值需要重新算。',
      metrics:[
        {name:'估值情景', simple:'把未来分成普通、很好、很差三种情况分别算。', read:'如果只有“完美情景”才能支撑价格，安全垫较薄。'},
        {name:'安全边际', simple:'实际价格和你保守估值之间留了多少余地。', read:'不是精确数字，而是避免必须所有假设都正确。'}
      ],
      site:'个股研究卡增加三情景估值和“哪些假设已被价格提前反映”。',
      sources:['https://blog.wenxuecity.com/myblog/82458/202606/']
    }
  ]
};

window.MYALPHA_STRATEGY_PLAYBOOK = {
  version:'5.1.1',
  principle:'经验先作为研究候选，不把市场情绪或单一指标机械转换成买卖信号。每条提醒都说明适用条件、不适用条件和最大风险。',
  strategies:[
    {id:'fear-sell-put',scene:'恐慌 / 大跌',name:'Sell Put 研究候选',plain:'只针对你本来就愿意以更低价格接货的股票。恐慌期波动率通常较高，权利金可能更有吸引力，但继续暴跌会带来接货风险。',params:'初筛：30–45 DTE；Delta 0.16–0.20。参数来自既有实战经验，属于待验证区间，不是统一最优值。',use:'基本逻辑未失效；无临近重大跳空事件；能够承受被指派；趋势至少停止加速恶化。',avoid:'Thesis 已破坏、只因为“跌很多”、不愿接货、财报/监管结果临近。',risk:'最大风险来自正股继续大跌；权利金只能提供有限缓冲。'},
    {id:'fear-buy-call',scene:'恐慌后的修复',name:'Buy Call 研究候选',plain:'适合已经出现较明确修复、但希望用有限权利金表达看涨观点的情况。不是“越跌越买 Call”。',params:'先看到期是否覆盖催化剂、IV是否过高、盈亏平衡价是否合理，再选行权价。',use:'趋势出现启动/二次启动或修复确认；有明确时间窗口。',avoid:'趋势仍持续恶化、只赌一天反弹、IV极高且没有催化剂。',risk:'方向正确但时间不够或IV回落，也可能亏损；最大损失可达全部权利金。'},
    {id:'fear-leaps',scene:'深度回撤 / 中长期看多',name:'LEAPS Call 研究候选',plain:'适合 QQQ 或研究充分的个股：中长期逻辑仍在，但需要更长时间等待修复和催化剂兑现。',params:'研究 12–24个月以上期限；重点比较 Delta、IV、盈亏平衡、时间价值和最大损失，不写死单一 Delta。',use:'长期 Thesis 清楚；回撤后停止持续恶化；到期远晚于核心催化剂；愿意承担权利金全部损失。',avoid:'只因为价格跌很多、基本面未确认、短期赌博、IV异常高却不比较成本。',risk:'LEAPS 仍有到期日；若恢复太慢或判断错误，长期 Call 仍可能大幅亏损甚至归零。'},
    {id:'greed-covered-call',scene:'贪婪 / 强势高位',name:'Covered Call 研究候选',plain:'已有正股且认为短期继续大涨空间有限时，可研究用卖 Call 换取权利金；代价是上涨收益可能被封顶。',params:'先比较执行价、到期日、被行权后是否愿意卖出正股。',use:'已有正股；Trend Pulse 高位钝化或上涨明显放缓；愿意在执行价卖出。',avoid:'强烈看多且不愿失去股票、即将有重大上行催化剂。',risk:'正股下跌仍由持有人承担；上涨过快时可能错失额外收益。'},
    {id:'greed-protective-put',scene:'贪婪 / 高位风险',name:'Protective Put 研究候选',plain:'已有重要持仓又担心尾部风险时，可研究买 Put 作为保险；它的核心不是赚钱，而是限制极端损失。',params:'先算保护区间、保险成本、期限与持仓相关性。',use:'不愿卖出长期持仓、但短期风险明显升高。',avoid:'保险成本过高、买保险后反而增加更高风险仓位。',risk:'如果市场不跌，权利金会成为持有成本。'}
  ]
};


window.MYALPHA_RULE_REGISTRY = {
  version:'5.1.0',
  principle:'规则中心只负责发现、解释和排序研究机会；不得自行修改核心阈值、不得自动下单。规则冲突时风险规则优先。',
  rules:[
    {id:'market-watch',agent:'Market Agent',module:'首页',status:'adopted',trigger:'NASDAQ≤-1.5% 或 S&P500≤-1.25% 或 VIX≥25',meaning:'市场波动明显升温，进入观察状态。',action:'开始检查关注股与期权环境，不直接交易。'},
    {id:'market-fear',agent:'Market Agent',module:'首页',status:'adopted',trigger:'NASDAQ≤-2.5% 或 S&P500≤-2.0% 或 VIX≥28',meaning:'单日大跌/恐慌环境。',action:'启动 Sell Put、Buy Call、LEAPS 研究候选扫描。'},
    {id:'market-panic',agent:'Market Agent',module:'首页',status:'adopted',trigger:'NASDAQ≤-4.0% 或 S&P500≤-3.5% 或 VIX≥35',meaning:'极端风险环境。',action:'风险优先；只保留能承受最坏结果的研究方案。'},
    {id:'correction-10',agent:'Market Agent',module:'核心ETF',status:'adopted',trigger:'指数距近期/历史高点回撤≥10%',meaning:'进入通常所说的调整区。',action:'与单日跌幅分开显示，按既有核心ETF规则判断。'},
    {id:'bear-20',agent:'Market Agent',module:'核心ETF',status:'adopted',trigger:'指数距高点回撤≥20%',meaning:'进入深度回撤/熊市级环境。',action:'强调分批与生存，不预测最低点。'},
    {id:'trend-restart',agent:'Stock Agent',module:'个股观察池',status:'adopted',trigger:'Trend Pulse 回踩后重新上拐',meaning:'回踩后重新转强。',action:'作为第二层确认，不替代 Thesis。'},
    {id:'trend-stall',agent:'Stock Agent',module:'个股观察池',status:'adopted',trigger:'高分区但斜率走平',meaning:'强势但上涨变慢。',action:'不因高分追涨，关注高位风险。'},
    {id:'trend-retreat',agent:'Risk Agent',module:'个股观察池',status:'adopted',trigger:'高分区斜率转负/趋势退潮',meaning:'分数仍高但正在转弱。',action:'压低机会优先级；Long Call/LEAPS 先等待。'},
    {id:'sell-put-fear',agent:'Options Agent',module:'期权',status:'research',trigger:'市场大跌 + 个股Thesis未失效 + 趋势未加速恶化',meaning:'恐慌环境中的低价接货研究。',action:'初筛30–45 DTE、|Delta| 0.16–0.20；必须愿意被指派。'},
    {id:'buy-call-repair',agent:'Options Agent',module:'期权',status:'research',trigger:'恐慌后出现趋势修复/二次启动',meaning:'有限权利金表达修复观点。',action:'先检查IV、DTE、催化剂时间，不做“越跌越买Call”。'},
    {id:'leaps-long-term',agent:'Options Agent',module:'期权',status:'research',trigger:'QQQ或研究充分个股深回撤后停止恶化，中长期Thesis仍成立',meaning:'给中长期判断更多兑现时间。',action:'优先研究12–24个月以上期限；比较Delta、IV、盈亏平衡和最大损失。'},
    {id:'greed-hedge',agent:'Risk Agent',module:'期权',status:'research',trigger:'强势高位 + 动能钝化',meaning:'高位不等于继续追涨。',action:'已有持仓可研究Covered Call或Protective Put的代价。'},
    {id:'thesis-required',agent:'Research Agent',module:'个股研究卡',status:'adopted',trigger:'个股进入高优先级候选',meaning:'没有Thesis就不能把技术信号升级为高优先级。',action:'至少写清论点、催化剂、风险、失效条件。'},
    {id:'data-freshness',agent:'Risk Agent',module:'全站',status:'adopted',trigger:'关键数据过期/缺失/回退',meaning:'数据质量优先于聪明推理。',action:'降级为“证据不足”，不输出确定性策略。'}
  ]
};


/* V6.8.2 · Source Hypothesis: lionhill / 狮山巡礼
   External method is preserved as research evidence and never overrides Production rules. */
if (!window.MYALPHA_RESEARCH_METHODS.authors.some(x=>x.id==='lionhill')) {
  window.MYALPHA_RESEARCH_METHODS.authors.push({id:'lionhill', name:'lionhill / 狮山巡礼'});
}
window.MYALPHA_RESEARCH_METHODS.methods.push({
  id:'tqqq-vs-leaps-rebound', author:'lionhill / 狮山巡礼', category:'杠杆与LEAPS',
  name:'QQQ大回调后的 TQQQ vs QQQ LEAPS 情境框架',
  plain:'QQQ出现约10%–15%回调后，不机械二选一。快速V型修复、长时间震荡、继续深跌，对TQQQ和LEAPS的风险来源不同。',
  action:'MyAlpha只在回调进入研究区后启动对比：同时检查MA20/50/200、VIX、市场宽度、TQQQ X2正式状态、LEAPS IV/Delta/DTE与流动性。',
  invalid:'如果QQQ尚未出现显著回调，或深熊仍在扩散，不把“跌很多”直接解释成加杠杆机会。外部作者的收益数字与情境结论必须由本站后续样本独立验证。',
  metrics:[
    {name:'TQQQ波动率拖累', simple:'TQQQ每日重置3倍杠杆，震荡路径本身会消耗净值。', read:'横盘反复时，即使QQQ最终回到原位，TQQQ也可能仍落后。'},
    {name:'LEAPS IV / Theta', simple:'长期Call也会受隐波回落和时间流逝影响。', read:'方向看对但IV下降、修复太慢，期权收益仍可能不理想。'},
    {name:'反弹速度', simple:'V型快速反弹与4–5个月震荡，对两类工具的影响不同。', read:'把“市场路径”作为工具选择的重要条件，而不是只看最终方向。'},
    {name:'Delta', simple:'ATM LEAPS约0.50；Deep ITM可更接近0.80–0.90。', read:'这里只保留为来源假设与合约筛选参考，不能替代实时IV/报价与风险预算。'}
  ],
  site:'策略中心新增“TQQQ vs QQQ LEAPS · 回调情境智能”；未来QQQ进入约8%–15%回调区时自动触发Agent研究任务，并在5/20/60日后验证情境判断。',
  sources:['https://blog.wenxuecity.com/myblog/82610/202610/1012.html']
});

window.MYALPHA_STRATEGY_PLAYBOOK.strategies.push({
  id:'qqq-rebound-leverage-choice', scene:'QQQ约10%–15%回调后的修复阶段',
  name:'TQQQ vs QQQ LEAPS · 情境研究候选',
  plain:'先判断市场路径，再比较工具。V型修复、震荡筑底、深熊延续分别面对Gamma/IV、Theta、每日重置和二次下探等不同风险。',
  params:'触发层只负责研究：QQQ约-8%开始观察，约-10%进入正式比较；-15%及以下提高研究优先级。LEAPS仍遵守本站单次≤1%、总LEAPS≤3%的既有约束。',
  use:'QQQ出现显著回调，并且开始出现MA20/MA50修复、VIX回落或市场宽度改善时。',
  avoid:'QQQ仍在MA200下方且VIX高压、宽度继续恶化、只因价格便宜而增加杠杆。',
  risk:'TQQQ有路径与波动率拖累；LEAPS有IV Crush、Theta与到期风险。两者都不是“回调越深越安全”。'
});

window.MYALPHA_RULE_REGISTRY.rules.push({
  id:'qqq-rebound-compare', agent:'Strategy Agent', module:'核心策略信号', status:'research',
  trigger:'QQQ距近252日高点回撤约8%开始观察；≥10%进入TQQQ vs QQQ LEAPS情境比较',
  meaning:'回调幅度只负责唤醒研究，不直接决定使用哪种杠杆工具。',
  action:'联合TQQQ X2、LEAPS Radar、VIX、MA20/50/200、Breadth与Cross-Asset；若深熊扩散，风险规则优先。'
});
