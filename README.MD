# Kurumsal İş ve Görev Yönetim Platformu

Kurum içi yazılım ve test ekiplerinin görev atamalarını, iş yükü kapasitelerini ve proje ilerlemelerini dinamik olarak takip edebilmesi amacıyla geliştirilmiş kapsamlı bir iş yönetim platformudur. Proje, standart bir yapılacaklar listesi uygulamasının ötesine geçerek; algoritmik iş yükü tahmini, veri bütünlüğü korunan efor takibi ve olay güdümlü bildirim mimarisi gibi kurumsal ihtiyaçlara yanıt verecek şekilde tasarlanmıştır.

---

## Öne Çıkan Mimari Özellikler

### 1. Rol Bazlı Yetkilendirme ve İzolasyon

Sistemde **Yönetici** ve **Çalışan** olmak üzere iki temel rol bulunur.

- **Yöneticiler:** Sadece kendi takımlarına ait görevleri, çalışanların iş yükü kapasitelerini ve darboğazları merkezi bir gösterge paneli üzerinden izleyebilir.
- **Çalışanlar:** Yalnızca kendilerine atanan veya iş ortağı olarak dahil oldukları görevleri görebilir ve yönetebilir.

### 2. Algoritmik İş Yükü Simülasyonu

Kişilerin üzerindeki kalan eforlar, kalan gün sayısına basitçe bölünmek yerine, görevin doğasına uygun matematiksel ağırlıklandırmalarla takvime dağıtılır:

- **Öncelik Bazlı:** Yüksek öncelikli işlerin yükü ilk günlere yığılırken, düşük öncelikliler ileri tarihlere kaydırılır.
- **Vade Bazlı:** Öğrenci sendromu simüle edilerek, teslim tarihine yaklaştıkça üstel olarak artan bir efor grafiği çizilir.
- **Büyüklük Bazlı:** Büyük çaplı görevlerde sürecin ilk %33'lük dilimine kurulum ve analiz maliyeti olarak %50 daha fazla efor atanır.

### 3. Güvenli Efor ve Yol Haritası Yönetimi

- Kullanıcılar görevler üzerinde alt adımlar oluşturabilir.
- Girilen efor kayıtları anlık olarak ana görevin harcanan efor metriklerini günceller.
- Geçmişe dönük kayıt manipülasyonları loglanır, geleceğe dönük efor girilmesi sunucu tarafında engellenir.

### 4. Olay Güdümlü Bildirim Sistemi

Veritabanında gerçekleşen tüm kritik işlemler (görev oluşturma, efor silme, yol haritası güncelleme) ilgili paydaşlara anında gelen kutusu bildirimi ve olarak iletilir.

---

## Kullanılan Teknolojiler

| Katman | Teknoloji |
|---|---|
| Arka Uç | Python 3, Django 4.x |
| Veritabanı | SQLite |
| Ön Yüz | HTML5, CSS3, Bootstrap 5 |
| Veri Görselleştirme | Chart.js |
| Versiyon Kontrol | Git & GitHub |

---

## Kurulum ve Çalıştırma

### 1. Repoyu Klonlayın ve Klasöre Girin

```bash
git clone <GITHUB_REPO_LINKI>
cd <PROJE_KLASÖR_ADI>
```

### 2. Sanal Ortam Oluşturun

```bash
python -m venv venv
source venv/bin/activate    # Mac/Linux
venv\Scripts\activate       # Windows
```

### 3. Gerekli Kütüphaneleri Yükleyin

```bash
pip install -r requirements.txt
```

### 4. Test Verilerini Üretin

Sistemi gerçekçi projeler, geçmiş efor kayıtları, gecikmiş işler ve bildirimlerle dolu bir ortamda test edebilmek için özel bir veri üretici script hazırlanmıştır. Aşağıdaki komut ile **2 Yönetici, 10 Çalışan, 2 Ekip ve 10'dan fazla detaylı görev senaryosu** otomatik olarak oluşturulacaktır:

```bash
python populate_test_data.py
```

> **Not:** Bu işlem mevcut veritabanını temizler ve sıfırdan tutarlı bir senaryo kurgular.

### 5. Sunucuyu Başlatın

```bash
python manage.py runserver
```

---

## Test Hesapları

`populate_test_data.py` komutunu çalıştırdıktan sonra aşağıdaki hesaplarla sisteme giriş yapabilir ve izole edilmiş yetkileri test edebilirsiniz.

> Tüm hesapların şifresi `123` olarak ayarlanmıştır.

### Yöneticiler

| Rol | Kullanıcı Adı |
|---|---|
| Yazılım Takım Lideri | `m.yilmaz` |
| Test Ekip Lideri | `a.kaya` |

### Çalışanlar

| Ekip | Kullanıcı Adları |
|---|---|
| Yazılım Ekibi | `a.demir`, `b.sahin`, `c.celik` |
| Test Ekibi | `f.koc` |