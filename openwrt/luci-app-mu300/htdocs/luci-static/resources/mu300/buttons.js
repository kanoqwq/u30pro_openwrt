'use strict';
'require baseclass';
'require rpc';
'require mu300.common as M';
var get=rpc.declare({object:'mu300dash',method:'button_get',nobatch:true,expect:{'':{}}});
var set=rpc.declare({object:'mu300dash',method:'button_set',params:['short','long'],nobatch:true,expect:{'':{}}});
var words={
 '实体按键':['Physical button','Fiziksel tuş'],
 '切卡键默认不执行任何动作。可分别设置短按和长按（3 秒），重启后保留。':['The SIM key has no action by default. Set short and long press (3 seconds) separately; settings survive reboot.','SIM tuşu varsayılan olarak işlem yapmaz. Kısa ve uzun basmayı (3 saniye) ayrı ayarlayın; yeniden başlatmada korunur.'],
 '短按':['Short press','Kısa basma'],'长按':['Long press','Uzun basma'],
 '无动作':['No action','İşlem yok'],'切换上网卡':['Switch data SIM','Veri SIM’ini değiştir'],
 '切换 Wi-Fi 频段':['Switch Wi-Fi band','Wi-Fi bandını değiştir'],
 '切换 NFC 开关':['Toggle NFC','NFC’yi aç/kapat'],
 '保存按键设置':['Save button settings','Tuş ayarlarını kaydet'],
 '正在保存…':['Saving…','Kaydediliyor…'],'已保存':['Saved','Kaydedildi'],
 '按键设置读取失败':['Unable to read button settings','Tuş ayarları okunamadı'],
 '按键设置保存失败':['Unable to save button settings','Tuş ayarları kaydedilemedi']
};
function t(s){var lang=M.uiLanguage();return lang==='zh'?s:(words[s]||[s,s])[lang==='tr'?1:0];}
function node(tag,text,cls){var n=document.createElement(tag);if(text)n.textContent=t(text);if(cls)n.className=cls;return n;}
return baseclass.extend({mount:function(root){
 var card=node('section',null,'mud-card mud-buttons');card.hidden=true;card.style.marginTop='14px';
 card.append(node('h3','实体按键'),node('p','切卡键默认不执行任何动作。可分别设置短按和长按（3 秒），重启后保留。','mud-note'));
 var selects=[],fields=node('div',null,'mud-device-grid');card.append(fields);
 ['短按','长按'].forEach(function(label,index){
  var row=node('div',null,'mud-device-field'),title=node('label',label),select=node('select');
  select.id='mud-button-'+index;title.htmlFor=select.id;
  [['none','无动作'],['data-switch','切换上网卡'],['wifi-band','切换 Wi-Fi 频段'],['nfc-toggle','切换 NFC 开关']].forEach(function(item){var option=node('option',item[1]);option.value=item[0];select.append(option);});
  row.append(title,select);fields.append(row);selects.push(select);
 });
 var save=node('button','保存按键设置','mud-btn'),result=node('p',null,'mud-note');save.type='button';result.setAttribute('role','status');card.append(save,result);root.append(card);
 var disposed=false,busy=true,loaded=false,writable=typeof L.hasViewPermission!=='function'||L.hasViewPermission();
 function disable(){save.disabled=busy||!loaded||!writable;selects.forEach(function(s){s.disabled=busy||!loaded||!writable;});card.setAttribute('aria-busy',String(busy));}
 function paint(r){if(!r||!r.ok)throw Error('invalid reply');card.hidden=!r.supported;if(!r.supported)return;selects.forEach(function(s,i){var value=r[i?'long':'short'];if(!['none','data-switch','wifi-band','nfc-toggle'].includes(value))throw Error('invalid action');s.value=value;});loaded=true;}
 disable();get().then(function(r){if(!disposed)paint(r);}).catch(function(){if(!disposed){card.hidden=false;result.textContent=t('按键设置读取失败');}}).finally(function(){busy=false;if(!disposed)disable();});
 save.onclick=function(){
  if(disposed||busy||!loaded||!writable)return;busy=true;disable();result.textContent=t('正在保存…');
  return set(selects[0].value,selects[1].value).then(function(r){if(disposed)return;paint(r);result.textContent=t('已保存');}).catch(function(){if(!disposed)result.textContent=t('按键设置保存失败');}).finally(function(){busy=false;if(!disposed)disable();});
 };
 return {dispose:function(){disposed=true;}};
}});
