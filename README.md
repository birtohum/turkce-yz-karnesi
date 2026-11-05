# Türkçe yapay zekâ karnesi

Yapay zekâ modelleri Türkiye'ye özgü bilgileri ne kadar biliyor? Bu depo, Wikidata'dan otomatik üretilmiş 1.479 soruyla (2.958 soru ifadesi) yerel açık modelleri ölçer ve sonuçları güven aralıklarıyla bir siteye döker.

**Site:** https://birtohum.github.io/turkce-yz-karnesi/

## Sonuçlar (5 Kasım 2026)

Altı kategorinin eşit ağırlıklı ortalaması, %95 bootstrap güven aralığı. Rastgele tahminle beklenen puan %31,4.

| Model | Genel | Nüfus (2 şık) | İlçe (4) | Plaka | Rakım (2) | Göl (4) | Doğum yılı (4) |
|---|---|---|---|---|---|---|---|
| Qwen3 14B | **49,7** [47,8–51,5] | 81 | 47 | 23 | 82 | 31 | 34 |
| Gemma 3 4B | 46,6 [44,6–48,6] | 77 | 60 | 19 | 52 | 39 | 32 |
| Qwen3 8B | 46,0 [44,0–48,0] | 76 | 44 | 20 | 70 | 32 | 35 |
| Llama 3.2 3B | 39,1 [37,2–40,9] | 60 | 45 | 16 | 52 | 32 | 29 |
| *Şans* | *31,4* | *50* | *25* | *13* | *50* | *25* | *25* |

- Gemma 3 4B ile Qwen3 8B arasındaki fark **anlamlı değil** (+0,6 puan, GA −1,9…+3,2). Diğer komşu farklar anlamlı ama küçük (Qwen3 14B − Gemma 3 4B: +3,1, GA 0,9…5,3).
- Göl ve doğum yılı sorularında tüm modeller şansa yakın.
- Konum yanlılığı büyük: Qwen3 14B dört şıklı sorularda doğru cevap A iken %76, B/C/D iken %22–27 başarılı.
- Tohum 8B ve Tohum 14B v2 (önceki bir projede Qwen3 üzerine yapılmış ince ayarlar) yanıtların %44 ve %96'sında harf yerine yeni bir soru ürettiği için sıralamaya alınmadı; ham yanıtları `results/public_raw/` içinde.

## Yöntem

- **Sorular** (`karne/generate.py`): Wikidata SPARQL. İl nüfusu karşılaştırma, ilçenin ili, plaka kodu (serbest yanıt + ters yön çoktan seçmeli), il merkezi rakımı karşılaştırma, göl/baraj gölünün ili, ünlülerin doğum yılı. Çelişkili ya da belirsiz kayıtlar atıldı (aynı plaka kodlu iki il, birden çok ilde aynı adlı ilçe/göl, birden çok ya da kaynaksız doğum tarihi, %15'ten yakın nüfuslar, 200 m'den yakın rakımlar, önceki sayımda sırası ters olan çiftler).
- **Varyantlar:** her soru iki kez sorulur; ikincisi farklı ifadeyle (nüfus/rakımda ters soru) ve doğru şık başka konumda. Doğru şıklar harflere dengeli dağıtılır.
- **Saklı bölüm:** soruların %20'si (`data/questions_heldout.json`) depoya konmaz; SHA-256 özeti `data/heldout.sha256` içinde. Üretim kodu açık olduğu için set yeniden üretilebilir; amaç gelecekteki modellerde açık/saklı farkını izlemek.
- **Modeller** (`karne/run.py`, `karne/queue.py`): Ollama, sıcaklık 0, düşünme kapalı, tek tek, RTX 3060 12 GB. Kuyruk GPU başka bir işle meşgulken bekler.
- **Puanlama** (`karne/grade.py`): deterministik; harf/sayı çözümlenemezse biçim hatası ya da ret, yanlış sayılır.
- **İstatistik** (`karne/stats.py`): soru başına iki ifadenin ortalaması; 10.000 tekrarlı yüzdelik bootstrap, genel puanda kategori içi yeniden örnekleme; model farkları eşleştirilmiş bootstrap.

## Sınırlar

- Doğru cevap Wikidata'nın söylediğidir; yakalanmayan Wikidata hataları sorularda kalmış olabilir (Konya ve Uşak'ın plaka kodları yanlış girilmişti, çakışmadan yakalandı).
- Yalnızca ücretsiz ve yerel çalışan küçük açık modeller ölçüldü. Ollama'nın bulut modeli ödeme istedi (HTTP 402); anahtar gerektiren API'ler denenmedi.
- Tek bir istem kalıbı; few-shot ya da başka istemler sonucu değiştirebilir.

## Çalıştırma

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
python -m karne.generate      # soruları üret (Wikidata)
python -m karne.queue         # modelleri sırayla çalıştır (Ollama)
python -m karne.analyze       # site/data/*.json
python -m pytest -q
```

## Lisans ve kaynak

Kod Apache-2.0. Sorular [Wikidata](https://www.wikidata.org/) verisinden (CC0) üretildi.
