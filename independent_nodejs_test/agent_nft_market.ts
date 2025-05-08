/**
 * Program IDL in camelCase format in order to be used in JS/TS.
 *
 * Note that this is only a type helper and is not the actual IDL. The original
 * IDL can be found at `target/idl/agent_nft_market.json`.
 */
export type AgentNftMarket = {
  "address": "3Qqf9EXWLDhr9bzxdgUk6UQbDYuynAS5WKT5ygpYpQfQ",
  "metadata": {
    "name": "agentNftMarket",
    "version": "0.1.0",
    "spec": "0.1.0",
    "description": "Agent NFT Subscription Service"
  },
  "instructions": [
    {
      "name": "getAllAgentNfts",
      "discriminator": [
        238,
        85,
        167,
        197,
        180,
        213,
        25,
        134
      ],
      "accounts": [
        {
          "name": "authority",
          "signer": true
        }
      ],
      "args": [],
      "returns": {
        "vec": {
          "defined": {
            "name": "agentNftInfo"
          }
        }
      }
    },
    {
      "name": "getUserAgentSubscription",
      "discriminator": [
        208,
        28,
        136,
        249,
        48,
        24,
        19,
        7
      ],
      "accounts": [
        {
          "name": "user",
          "signer": true
        },
        {
          "name": "agentNftMint"
        },
        {
          "name": "agentNft",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  97,
                  103,
                  101,
                  110,
                  116,
                  45,
                  110,
                  102,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "agentNftMint"
              }
            ]
          }
        },
        {
          "name": "subscription",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  115,
                  117,
                  98,
                  115,
                  99,
                  114,
                  105,
                  112,
                  116,
                  105,
                  111,
                  110
                ]
              },
              {
                "kind": "account",
                "path": "user"
              },
              {
                "kind": "account",
                "path": "agentNftMint"
              }
            ]
          }
        }
      ],
      "args": [],
      "returns": {
        "defined": {
          "name": "subscriptionInfo"
        }
      }
    },
    {
      "name": "getUserSubscriptions",
      "discriminator": [
        70,
        242,
        39,
        146,
        213,
        249,
        69,
        204
      ],
      "accounts": [
        {
          "name": "user",
          "signer": true
        }
      ],
      "args": [],
      "returns": {
        "vec": {
          "defined": {
            "name": "subscriptionInfo"
          }
        }
      }
    },
    {
      "name": "mintAgentNft",
      "discriminator": [
        57,
        195,
        246,
        106,
        161,
        195,
        27,
        112
      ],
      "accounts": [
        {
          "name": "owner",
          "writable": true,
          "signer": true
        },
        {
          "name": "programAuthority"
        },
        {
          "name": "mint",
          "writable": true,
          "signer": true
        },
        {
          "name": "agentNft",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  97,
                  103,
                  101,
                  110,
                  116,
                  45,
                  110,
                  102,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "mint"
              }
            ]
          }
        },
        {
          "name": "tokenAccount",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "account",
                "path": "owner"
              },
              {
                "kind": "const",
                "value": [
                  6,
                  221,
                  246,
                  225,
                  215,
                  101,
                  161,
                  147,
                  217,
                  203,
                  225,
                  70,
                  206,
                  235,
                  121,
                  172,
                  28,
                  180,
                  133,
                  237,
                  95,
                  91,
                  55,
                  145,
                  58,
                  140,
                  245,
                  133,
                  126,
                  255,
                  0,
                  169
                ]
              },
              {
                "kind": "account",
                "path": "mint"
              }
            ],
            "program": {
              "kind": "const",
              "value": [
                140,
                151,
                37,
                143,
                78,
                36,
                137,
                241,
                187,
                61,
                16,
                41,
                20,
                142,
                13,
                131,
                11,
                90,
                19,
                153,
                218,
                255,
                16,
                132,
                4,
                142,
                123,
                216,
                219,
                233,
                248,
                89
              ]
            }
          }
        },
        {
          "name": "tokenProgram",
          "address": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        },
        {
          "name": "associatedTokenProgram",
          "address": "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
        },
        {
          "name": "systemProgram",
          "address": "11111111111111111111111111111111"
        },
        {
          "name": "rent",
          "address": "SysvarRent111111111111111111111111111111111"
        },
        {
          "name": "clock",
          "docs": [
            "Required for accessing clock"
          ],
          "address": "SysvarC1ock11111111111111111111111111111111"
        }
      ],
      "args": [
        {
          "name": "metadataUrl",
          "type": "string"
        }
      ]
    },
    {
      "name": "purchaseSubscription",
      "discriminator": [
        219,
        151,
        184,
        220,
        138,
        36,
        203,
        237
      ],
      "accounts": [
        {
          "name": "user",
          "writable": true,
          "signer": true
        },
        {
          "name": "agentNft",
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  97,
                  103,
                  101,
                  110,
                  116,
                  45,
                  110,
                  102,
                  116
                ]
              },
              {
                "kind": "account",
                "path": "agentNftMint"
              }
            ]
          }
        },
        {
          "name": "agentNftMint"
        },
        {
          "name": "subscription",
          "writable": true,
          "pda": {
            "seeds": [
              {
                "kind": "const",
                "value": [
                  115,
                  117,
                  98,
                  115,
                  99,
                  114,
                  105,
                  112,
                  116,
                  105,
                  111,
                  110
                ]
              },
              {
                "kind": "account",
                "path": "user"
              },
              {
                "kind": "account",
                "path": "agentNftMint"
              }
            ]
          }
        },
        {
          "name": "paymentDestination",
          "writable": true
        },
        {
          "name": "systemProgram",
          "address": "11111111111111111111111111111111"
        },
        {
          "name": "clock",
          "docs": [
            "Required for accessing clock"
          ],
          "address": "SysvarC1ock11111111111111111111111111111111"
        }
      ],
      "args": [
        {
          "name": "subscriptionType",
          "type": {
            "defined": {
              "name": "subscriptionType"
            }
          }
        }
      ]
    }
  ],
  "accounts": [
    {
      "name": "agentNft",
      "discriminator": [
        237,
        215,
        176,
        20,
        217,
        193,
        90,
        153
      ]
    },
    {
      "name": "subscription",
      "discriminator": [
        64,
        7,
        26,
        135,
        102,
        132,
        98,
        33
      ]
    }
  ],
  "errors": [
    {
      "code": 6000,
      "name": "onlyOwnerCanMint",
      "msg": "Only the owner can mint NFTs"
    },
    {
      "code": 6001,
      "name": "invalidPaymentAmount",
      "msg": "Invalid payment amount"
    },
    {
      "code": 6002,
      "name": "invalidSubscriptionType",
      "msg": "Invalid subscription type"
    },
    {
      "code": 6003,
      "name": "metadataUrlTooLong",
      "msg": "Metadata URL too long"
    },
    {
      "code": 6004,
      "name": "paymentFailed",
      "msg": "Payment failed"
    },
    {
      "code": 6005,
      "name": "nftNotFound",
      "msg": "NFT not found"
    },
    {
      "code": 6006,
      "name": "subscriptionNotFound",
      "msg": "Subscription not found"
    },
    {
      "code": 6007,
      "name": "unauthorized",
      "msg": "Unauthorized access"
    }
  ],
  "types": [
    {
      "name": "agentNft",
      "type": {
        "kind": "struct",
        "fields": [
          {
            "name": "owner",
            "type": "pubkey"
          },
          {
            "name": "mint",
            "type": "pubkey"
          },
          {
            "name": "metadataUrl",
            "type": "string"
          },
          {
            "name": "createdAt",
            "type": "i64"
          },
          {
            "name": "bump",
            "type": "u8"
          }
        ]
      }
    },
    {
      "name": "agentNftInfo",
      "type": {
        "kind": "struct",
        "fields": [
          {
            "name": "address",
            "type": "pubkey"
          },
          {
            "name": "mint",
            "type": "pubkey"
          },
          {
            "name": "owner",
            "type": "pubkey"
          },
          {
            "name": "metadataUrl",
            "type": "string"
          },
          {
            "name": "createdAt",
            "type": "i64"
          }
        ]
      }
    },
    {
      "name": "subscription",
      "type": {
        "kind": "struct",
        "fields": [
          {
            "name": "user",
            "type": "pubkey"
          },
          {
            "name": "agentNftMint",
            "type": "pubkey"
          },
          {
            "name": "expiresAt",
            "type": "i64"
          },
          {
            "name": "bump",
            "type": "u8"
          }
        ]
      }
    },
    {
      "name": "subscriptionInfo",
      "type": {
        "kind": "struct",
        "fields": [
          {
            "name": "agentNftMint",
            "type": "pubkey"
          },
          {
            "name": "metadataUrl",
            "type": "string"
          },
          {
            "name": "expiresAt",
            "type": "i64"
          }
        ]
      }
    },
    {
      "name": "subscriptionType",
      "type": {
        "kind": "enum",
        "variants": [
          {
            "name": "oneDay"
          },
          {
            "name": "sevenDays"
          },
          {
            "name": "thirtyDays"
          },
          {
            "name": "year"
          }
        ]
      }
    }
  ]
};
