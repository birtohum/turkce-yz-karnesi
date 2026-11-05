# Türkçe yapay zekâ karnesi

Yapay zekâ modelleri Türkiye'ye özgü bilgileri ne kadar biliyor? Bu depo, Wikidata'dan otomatik üretilmiş 1.479 soruyla (2.958 soru ifadesi) yerel açık modelleri ve Meta Model API modellerini ölçer ve sonuçları güven aralıklarıyla bir siteye döker.

**Site:** https://birtohum.github.io/turkce-yz-karnesi/

## Sonuçlar (5 Kasım 2026)

1.209 açık soru (2.418 ifade); altı kategorinin eşit ağırlıklı ortalaması, %95 bootstrap güven aralığı. Rastgele tahminle beklenen puan %31,3. Meta modelleri Meta Model API üzerinden, diğerleri yerelde Ollama ile çalıştı.

| Model | Genel | Nüfus (2 şık) | İlçe (4) | Plaka | Rakım (2) | Göl (4) | Doğum yılı (4) |
|---|---|---|---|---|---|---|---|
| Muse Wonder 1.0 (API) | **98,6** [97,7–99,4] | 100 | 100 | 100 | 99 | 93 | 100 |
| Muse Spark 1.1 (API) | 98,3 [97,4–99,2] | 100 | 100 | 100 | 100 | 91 | 100 |
| Muse Spark 1.3 (API) | 97,8 [96,8–98,8] | 100 | 100 | 100 | 100 | 88 | 99 |
| Muse Spark 1.2 (c) (API) | 97,8 [96,8–98,7] | 100 | 100 | 100 | 99 | 89 | 100 |
| Muse Spark 1.2 (API) | 97,7 [96,7–98,6] | 100 | 99 | 100 | 100 | 88 | 99 |
| Muse Spark 1.3 (c) (API) | 97,7 [96,6–98,7] | 100 | 100 | 100 | 100 | 87 | 99 |
| Qwen3 14B | 49,2 [47,2–51,3] | 80 | 47 | 23 | 81 | 32 | 33 |
| Gemma 3 4B | 46,6 [44,5–48,7] | 76 | 60 | 17 | 54 | 40 | 33 |
| Qwen3 8B | 46,1 [43,8–48,3] | 76 | 45 | 20 | 69 | 33 | 34 |
| Llama 3.2 3B | 38,9 [36,8–40,8] | 59 | 46 | 18 | 51 | 31 | 29 |
| *Şans* | *31,3* | *50* | *25* | *13* | *50* | *25* | *25* |

- **Uçurum:** Meta'nın altı modeli %97,7–98,6 aralığında; yerel en iyi model %49. Büyük modeller arasındaki farklar 1 puanın altında, bu set artık onları ayırt etmiyor.
- Meta modellerinin hatalarının önemli kısmı göl kategorisinde ve elle bakılanların bir bölümü Wikidata'daki hatalı/belirsiz kayıtlar (sitede “Tartışmalı sorular”).
- Konum yanlılığı küçük modellerde büyük: Qwen3 14B dört şıklı sorularda doğru cevap A iken %77, B/C/D iken %21–27 başarılı. Meta modellerinde her harfte %96–100; ikinci tekrarda yanıtların %99'u aynı.
- Tohum 8B ve Tohum 14B v2 (önceki bir projede Qwen3 üzerine yapılmış ince ayarlar) yanıtların %45 ve %96'sında harf yerine yeni bir soru ürettiği için sıralamaya alınmadı; ham yanıtları `results/public_raw/` içinde.
- Meta API harcaması: 35,37 $ (29.031 istek; her model iki kez).

## Yöntem

- **Sorular** (`karne/generate.py`): Wikidata SPARQL. İl nüfusu karşılaştırma, ilçenin ili, plaka kodu (serbest yanıt + ters yön çoktan seçmeli), il merkezi rakımı karşılaştırma, göl/baraj gölünün ili, ünlülerin doğum yılı. Çelişkili ya da belirsiz kayıtlar atıldı (aynı plaka kodlu iki il, birden çok ilde aynı adlı ilçe/göl, birden çok ya da kaynaksız doğum tarihi, %15'ten yakın nüfuslar, 200 m'den yakın rakımlar, önceki sayımda sırası ters olan çiftler).
- **Varyantlar:** her soru iki kez sorulur; ikincisi farklı ifadeyle (nüfus/rakımda ters soru) ve doğru şık başka konumda. Doğru şıklar harflere dengeli dağıtılır.
- **Saklı bölüm:** soruların %20'si (`data/questions_heldout.json`) depoya konmaz; SHA-256 özeti `data/heldout.sha256` içinde. Üretim kodu açık olduğu için set yeniden üretilebilir; amaç gelecekteki modellerde açık/saklı farkını izlemek.
- **Modeller** (`karne/run.py`, `karne/queue.py`): Ollama, sıcaklık 0, düşünme kapalı, tek tek, RTX 3060 12 GB. Kuyruk GPU başka bir işle meşgulken bekler.
- **Puanlama** (`karne/grade.py`): deterministik; harf/sayı çözümlenemezse biçim hatası ya da ret, yanlış sayılır.
- **İstatistik** (`karne/stats.py`): soru başına iki ifadenin ortalaması; 10.000 tekrarlı yüzdelik bootstrap, genel puanda kategori içi yeniden örnekleme; model farkları eşleştirilmiş bootstrap.

## Sınırlar

- Doğru cevap Wikidata'nın söylediğidir; yakalanmayan Wikidata hataları sorularda kalmış olabilir (Konya ve Uşak'ın plaka kodları yanlış girilmişti, çakışmadan yakalandı).
- Yerel modeller küçük ve akıl yürütmesiz, Meta modelleri büyük ve akıl yürütmeli; aradaki fark yalnız bilgi değil. OpenAI, Anthropic, Google gibi diğer ticari modeller bu turda yok.
- Tek bir istem kalıbı; few-shot ya da başka istemler sonucu değiştirebilir.

## Çalıştırma

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
python -m karne.generate      # soruları üret (Wikidata)
python -m karne.queue         # yerel modeller (Ollama)
sh karne/queue_meta.sh        # Meta modelleri (META_MODEL_API_KEY gerekir)
python -m karne.analyze       # site/data/*.json
python -m pytest -q
```

## Lisans ve kaynak

Kod Apache-2.0. Sorular [Wikidata](https://www.wikidata.org/) verisinden (CC0) üretildi.
