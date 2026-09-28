window.MYALPHA_RESEARCH_METHODS = {
  version: '4.9.6',
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
