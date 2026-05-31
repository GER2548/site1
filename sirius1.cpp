#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(NULL);
    long long n,m,mx=0,k=-1,mn=10000000000;
    cin >> n >> m;
    vector<long long> l;
    for (int i=0;i<n;i++){
        long long x;
        cin >> x;
        l.push_back(x);
        mx+=x;
        if (x>k){
            k=x;
        }
        if (x<mn){
            mn=x;
        }
    }
    if (mn>=m){
        cout<<mx+l.size()-1;
    } else {
        cout<<k;
    }
}

