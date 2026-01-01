from django import forms

class ProxyImportForm(forms.Form):
    # 用于粘贴代理的文本框
    proxy_text = forms.CharField(
        label="粘贴代理地址",
        widget=forms.Textarea(attrs={'rows': 10, 'placeholder': '每行一个，格式: host:port:username:password (例如: isp.decodo.com:10001:user:pass)'}),
        required=False
    )
    # 用于上传 data.csv 的文件框
    proxy_file = forms.FileField(
        label="上传 CSV 文件",
        required=False
    )