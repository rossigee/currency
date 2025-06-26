# Multi-sig wallet compatibility tests

## Test key 1

I created a test wallet with Electrum using the BIP39 mnemonic...

```
index hen portion capital alley name demise wasp bulb evidence utility beach
```

Configured with 'legacy' (p2pkh) derivation (m/44/0/0) it gave me:

* public key: `xpub6CFMcc1RHDFfhVtzgLBgyHrzMR7qoXtC2VbwBm9h7Aj8F3X6ndqPVTbBQb8xCpW1RSJ7PKM2Fz9sK4obK7soq6EnsSKhvB7rGLmMCkBfPmY`
* BIP32 root fingerprint: `4b4e812f`

The first legacy addresses were:

* `19J3rrKgQyqZtXkVoX8KLxNTqJkh7xh2ao`
* `1PcyVXNQfAntVhHxt4wvyyFzFE1rPH9Y6G`
* `1KzYLgXcQCQhosSTxLjh9oVdZ4oQtc4xru`

Configured with 'native segwit' (p2wpkh) with a derivation of (m/84/0/0) it gave me:

* public key: `zpub6qV14UeJGiD1EPyfMgCadQuVoGPKyFiSwgz9KMebY5VJHWAEKxfQfSYTFtVwykLTZQCpM1Ld77n5H3JyumgoPyzLn56bQNxfd7Kk1AkhuNP`
* BIP32 root fingerprint: fingerprint: `4b4e812f`
* converted to xpub: `xpub6BpUT9JTyM83XobRgxdLDEiVTL6S61jT7TwhkZrpn4jYBJXmpeLHRKEBDUamyw2ck7yCr49WBo4yWU5rUNrmoWd93PhkEZKh5fCTE2Jxs7Q`

The first segwit addresses were:

* `bc1qaj6lq4y5wj6r8nx5cu77rx970ax9s0xyh5tdfy`
* `bc1qfa355xv083mylpnthspc4mm97zkr448zgcek97`
* `bc1qda4fzput8dzx8mz9u6j0slclamp3f5c3nxufew`

Grok has confirmed that an xpub from a BIP44 (legacy) or BIP84 (native SegWit) derivation path can be used in a multisig wallet as long as the wallet creator knows to the use the correct address type (e.g., p2sh for BIP44 or p2wsh for BIP84) to set up the multisig correctly.

## Test key 2

I created another key in Sparrow wallet...

```
scan innocent area cargo blade task suspect obtain basket crane raven void
```

Configured with 'legacy' (p2pkh) derivation (m/44/0/0) it gave me:

* public key: `xpub6DGvx3kdwy2byeM9TFey7VPsAEY4sU6yy87p3za8w5RAA8vbEDrQM2BjAYQTdtH71FV211vnUrb64svXMDMyKqAF5g4xcJk5TS2YHGTPb6v`
* BIP32 root fingerprint: `0ff47bbc`

Configured with 'native segwit' (p2wpkh) with a derivation of (m/84/0/0) it gave me:

* public key: `zpub6rJPijSDvYUQnHP1h6YERayvNT2hrvrtdF251boEFQ1mPhBwEX8aB1isyqDcggPPBQC3uKaq2xkYRUgVCBuwdanWTUNnPtPwQAQUiXruv8Q`
* public key (as xpub): `xpub6Cds7Q6PdBPT5gzn2Nxz1Qnv2Wjoygsto1ydSp1TVPG1HVZUjCoSvtQbwRJSgs5YN7xSQNPi7e3SeuTMko5v37RJinywE4kxriHBwQLYftm`
* BIP32 root fingerprint: fingerprint: `0ff47bbc`

## Test key 3

I used my ColdCard to generate a temporary 12 word seed for this...

```
cradle veteran scout depth head step exact post attitude current analyst dry
```

On generation it declared it's XFP to be `d7401a5b`.

It declares it's BIP44 xpub to be:

* public key: `xpub6DJzE193Fm6mygdwULPuncBikU6yMF114HVYUUUWBzK3J4wWYHpkhcagbMKAK2LeGTJ6Gx2a8DMmznDrX4xDhixD6E7Cc3V7ZCJfdCoGECC`

and it's BIP84...

* public key: `zpub6rxgGCQ21tu2XmrRHvfwCX9cb9bCtAALXDCFLq8pGzpoEsEYK7FqvavaagZ8EzFxzQqWsooGtTRod2Fcaz41fRRGTVNMnbDdPenTYvW24vX`
* converted: `xpub6DJ9es4BiXp4qBUBdD6gnLxcFDJJzvBLgz9on3M3Wz538fc5onvigTcJYGdxFAx8B8buNrc9y8ihrT2V9bDz4x44ioyWcmaerCfAmjbMRqt`

# Multisig wallet creation

Legacy:

xpub6CFMcc1RHDFfhVtzgLBgyHrzMR7qoXtC2VbwBm9h7Aj8F3X6ndqPVTbBQb8xCpW1RSJ7PKM2Fz9sK4obK7soq6EnsSKhvB7rGLmMCkBfPmY
xpub6DGvx3kdwy2byeM9TFey7VPsAEY4sU6yy87p3za8w5RAA8vbEDrQM2BjAYQTdtH71FV211vnUrb64svXMDMyKqAF5g4xcJk5TS2YHGTPb6v
xpub6DJzE193Fm6mygdwULPuncBikU6yMF114HVYUUUWBzK3J4wWYHpkhcagbMKAK2LeGTJ6Gx2a8DMmznDrX4xDhixD6E7Cc3V7ZCJfdCoGECC

Segwit keys:

xpub6BpUT9JTyM83XobRgxdLDEiVTL6S61jT7TwhkZrpn4jYBJXmpeLHRKEBDUamyw2ck7yCr49WBo4yWU5rUNrmoWd93PhkEZKh5fCTE2Jxs7Q
xpub6Cds7Q6PdBPT5gzn2Nxz1Qnv2Wjoygsto1ydSp1TVPG1HVZUjCoSvtQbwRJSgs5YN7xSQNPi7e3SeuTMko5v37RJinywE4kxriHBwQLYftm
xpub6DJ9es4BiXp4qBUBdD6gnLxcFDJJzvBLgz9on3M3Wz538fc5onvigTcJYGdxFAx8B8buNrc9y8ihrT2V9bDz4x44ioyWcmaerCfAmjbMRqt

## Electrum

With Electrum, creating a (p2sh) multisig 2-3 using the above BIP44 keys.

Initial 'receive' addresses:

* `3JWQzwuKKicTNNyGtwENukjUhr4yT9E46h`
* `3FvuhNi8jYrwiy5sPyaSZjP7x2kJ3D4Sj4`
* `33m8gt1eFvc5D6J2WzqoDDBoFv6Wfwvyda`

Also, a p2sh using the BIP84 keys. Initial addresses:

* `3MQSdWBqfLetuuNkvhKMReUBjXBihoA1MF`
* `3GmBBiHpJVhErXrdmeegHwsB42S574nkQg`
* `377P5sWhEbgNREdrH4JB3bbEAwM62D1w82`

## Sparrow

Created the following 'p2sh' wallet with BIP44s:

```
sh(sortedmulti(2,[4b4e812f/44h/0h/0h]xpub6CFMcc1RHDFfhVtzgLBgyHrzMR7qoXtC2VbwBm9h7Aj8F3X6ndqPVTbBQb8xCpW1RSJ7PKM2Fz9sK4obK7soq6EnsSKhvB7rGLmMCkBfPmY/<0;1>/*,[d7401a5b/44h/0h/0h]xpub6DJzE193Fm6mygdwULPuncBikU6yMF114HVYUUUWBzK3J4wWYHpkhcagbMKAK2LeGTJ6Gx2a8DMmznDrX4xDhixD6E7Cc3V7ZCJfdCoGECC/<0;1>/*,[0ff47bbc/44h/0h/0h]xpub6DGvx3kdwy2byeM9TFey7VPsAEY4sU6yy87p3za8w5RAA8vbEDrQM2BjAYQTdtH71FV211vnUrb64svXMDMyKqAF5g4xcJk5TS2YHGTPb6v/<0;1>/*))#krq758q5
```

Initial 'receive' addresses match Electrum:

* `3JWQzwuKKicTNNyGtwENukjUhr4yT9E46h`
* `3FvuhNi8jYrwiy5sPyaSZjP7x2kJ3D4Sj4`
* `33m8gt1eFvc5D6J2WzqoDDBoFv6Wfwvyda`

And with BIP84s:

```
sh(sortedmulti(2,[0ff47bbc/84h/0h/0h]xpub6Cds7Q6PdBPT5gzn2Nxz1Qnv2Wjoygsto1ydSp1TVPG1HVZUjCoSvtQbwRJSgs5YN7xSQNPi7e3SeuTMko5v37RJinywE4kxriHBwQLYftm/<0;1>/*,[d7401a5b/84h/0h/0h]xpub6DJ9es4BiXp4qBUBdD6gnLxcFDJJzvBLgz9on3M3Wz538fc5onvigTcJYGdxFAx8B8buNrc9y8ihrT2V9bDz4x44ioyWcmaerCfAmjbMRqt/<0;1>/*,[4b4e812f/84h/0h/0h]xpub6BpUT9JTyM83XobRgxdLDEiVTL6S61jT7TwhkZrpn4jYBJXmpeLHRKEBDUamyw2ck7yCr49WBo4yWU5rUNrmoWd93PhkEZKh5fCTE2Jxs7Q/<0;1>/*))#aevej65u
```

Initial addresses also match Electrum:

* `3MQSdWBqfLetuuNkvhKMReUBjXBihoA1MF`
* `3GmBBiHpJVhErXrdmeegHwsB42S574nkQg`
* `377P5sWhEbgNREdrH4JB3bbEAwM62D1w82`

Now for a 'Native Segwit (P2WPKH)' multi-sig, which Electrum didn't appear able to create.

```
wsh(sortedmulti(2,[0ff47bbc/48h/0h/0h/2h]xpub6Cds7Q6PdBPT5gzn2Nxz1Qnv2Wjoygsto1ydSp1TVPG1HVZUjCoSvtQbwRJSgs5YN7xSQNPi7e3SeuTMko5v37RJinywE4kxriHBwQLYftm/<0;1>/*,[d7401a5b/48h/0h/0h/2h]xpub6DJ9es4BiXp4qBUBdD6gnLxcFDJJzvBLgz9on3M3Wz538fc5onvigTcJYGdxFAx8B8buNrc9y8ihrT2V9bDz4x44ioyWcmaerCfAmjbMRqt/<0;1>/*,[4b4e812f/48h/0h/0h/2h]xpub6BpUT9JTyM83XobRgxdLDEiVTL6S61jT7TwhkZrpn4jYBJXmpeLHRKEBDUamyw2ck7yCr49WBo4yWU5rUNrmoWd93PhkEZKh5fCTE2Jxs7Q/<0;1>/*))#qtts5t87
```

Initial addresses:

* `bc1qpl8hc6rtwcmqhg74wtxle7v7d443whxt4agruk8tfpynsxa0r46s8tencf`
* `bc1qdg88877wquhjyapnvpcnexsqnscax9wvr0ug8254aphqqq076nssjgupp4`
* `bc1qp56tq2y82c3zutp2l324hall56f8kjt8gqp0gjh3lg4wfa5rru4qaggduq`




## The big payback

```

```
