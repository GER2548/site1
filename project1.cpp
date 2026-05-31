#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(NULL);
    long long x,y,a,b,c;
    cin >> x>>y >>a>>b>>c;
    long long mx=0;
    if ((a>x && a>y) || (b>y && b>x)){
        cout<<0;
        return 0;
    }
    if (x%a>b){
        mx=max((x/a)+(y/b),mx);
    } else {
        mx=max((x/a),mx);
    }
    mx=max(mx,(y/a)*(x/b));
    cout<<mx;
}


